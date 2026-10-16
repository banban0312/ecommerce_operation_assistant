from collections.abc import Generator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import (
    get_workspace_access,
    require_admin,
    require_high_risk_approval,
)
from app.api.routes.auth import router as auth_router
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    AuditEvent,
    Base,
    MembershipStatus,
    User,
    UserStatus,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from app.services.auth import AuthTokenError, create_access_token, parse_access_token
from app.services.users import hash_password, verify_password
from app.services.workspaces import WorkspaceAccess


@pytest.fixture
def auth_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-" + "x" * 48)
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.state.engine = engine

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db

    @app.get("/_test/workspace")
    def workspace_probe(access: Annotated[WorkspaceAccess, Depends(get_workspace_access)]):
        return {"workspace_id": access.workspace.id, "role": access.role}

    @app.get("/_test/admin")
    def admin_probe(access: Annotated[WorkspaceAccess, Depends(require_admin)]):
        return {"role": access.role}

    @app.get("/_test/high-risk")
    def high_risk_probe(access: Annotated[WorkspaceAccess, Depends(require_high_risk_approval)]):
        return {"role": access.role}

    with Session(engine) as db:
        workspace = Workspace(slug="shop", name="示例工作区")
        user = User(
            email="operator@example.com",
            display_name="运营人员",
            password_hash=hash_password("a-long-test-password"),
            status=UserStatus.ACTIVE.value,
        )
        db.add_all([workspace, user])
        db.flush()
        db.add(
            WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.OPERATOR.value,
                status=MembershipStatus.ACTIVE.value,
            )
        )
        db.commit()
        app.state.test_user_id = user.id
        app.state.test_workspace_id = workspace.id
        other_workspace = Workspace(slug="other", name="其他工作区")
        db.add(other_workspace)
        db.commit()
        app.state.other_workspace_id = other_workspace.id

    try:
        yield TestClient(app), engine, app
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def test_password_hash_and_signed_token(auth_app) -> None:
    _, engine, app = auth_app
    encoded = hash_password("correct-password")
    assert encoded != "correct-password"
    assert verify_password("correct-password", encoded)
    assert not verify_password("wrong-password", encoded)
    with Session(engine) as db:
        user = db.get(User, app.state.test_user_id)
        token = create_access_token(user)
    assert parse_access_token(token)["sub"] == str(app.state.test_user_id)
    with pytest.raises(AuthTokenError):
        parse_access_token(token + "tampered")


def test_login_and_current_identity(auth_app) -> None:
    client, _, app = auth_app
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "OPERATOR@example.com", "password": "a-long-test-password"},
    )
    assert login.status_code == 200
    payload = login.json()
    assert payload["user"]["memberships"][0]["role"] == "operator"
    assert "password_hash" not in payload["user"]

    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["id"] == app.state.test_user_id


def test_wrong_password_and_missing_token_are_rejected(auth_app) -> None:
    client, _, _ = auth_app
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "operator@example.com", "password": "incorrect"}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cross_workspace_access_is_denied(auth_app) -> None:
    client, _, app = auth_app
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "operator@example.com", "password": "a-long-test-password"},
    ).json()
    response = client.get(
        "/_test/workspace",
        headers={
            "Authorization": f"Bearer {login['access_token']}",
            "X-Workspace-ID": str(app.state.other_workspace_id),
        },
    )
    assert response.status_code == 403


def test_operator_cannot_admin_or_approve_high_risk(auth_app) -> None:
    client, engine, app = auth_app
    with Session(engine) as db:
        user = db.get(User, app.state.test_user_id)
        token = create_access_token(user)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(app.state.test_workspace_id),
    }
    assert client.get("/_test/admin", headers=headers).status_code == 403
    assert client.get("/_test/high-risk", headers=headers).status_code == 403
    assert (
        client.get(
            f"/api/v1/auth/workspaces/{app.state.test_workspace_id}/members",
            headers=headers,
        ).status_code
        == 403
    )


def test_supervisor_can_approve_high_risk_but_cannot_manage_settings(auth_app) -> None:
    client, engine, app = auth_app
    with Session(engine) as db:
        membership = db.scalar(
            select(WorkspaceMembership).where(WorkspaceMembership.user_id == app.state.test_user_id)
        )
        membership.role = WorkspaceRole.SUPERVISOR.value
        db.commit()
        token = create_access_token(db.get(User, app.state.test_user_id))
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(app.state.test_workspace_id),
    }
    assert client.get("/_test/high-risk", headers=headers).status_code == 200
    assert client.get("/_test/admin", headers=headers).status_code == 403


def test_admin_can_add_member_and_audit_it(auth_app) -> None:
    client, engine, app = auth_app
    with Session(engine) as db:
        membership = db.scalar(
            select(WorkspaceMembership).where(WorkspaceMembership.user_id == app.state.test_user_id)
        )
        membership.role = WorkspaceRole.ADMIN.value
        db.commit()
        token = create_access_token(db.get(User, app.state.test_user_id))
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(app.state.test_workspace_id),
    }
    members_url = f"/api/v1/auth/workspaces/{app.state.test_workspace_id}/members"
    before = client.get(members_url, headers=headers)
    assert before.status_code == 200
    assert len(before.json()) == 1
    created = client.post(
        f"/api/v1/auth/workspaces/{app.state.test_workspace_id}/members",
        headers=headers,
        json={
            "email": "supervisor@example.com",
            "display_name": "运营主管",
            "password": "another-long-password",
            "role": "supervisor",
        },
    )
    assert created.status_code == 201
    assert created.json()["role"] == "supervisor"
    members = client.get(members_url, headers=headers)
    assert members.status_code == 200
    assert len(members.json()) == 2
    assert {member["role"] for member in members.json()} == {"admin", "supervisor"}
    assert all("password_hash" not in member for member in members.json())
    with Session(engine) as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "workspace.member_created"))
        assert event is not None
        assert event.actor_user_id == app.state.test_user_id
        assert event.workspace_id == app.state.test_workspace_id
        assert event.created_at is not None
