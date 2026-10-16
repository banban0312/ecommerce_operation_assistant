"""M3 配置权限、持久化、脱敏与连接检查验收。"""

from collections.abc import Generator
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditEvent,
    Base,
    PlatformAccountPlaceholder,
    Store,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.services.auth import create_access_token
from app.services.users import hash_password


@pytest.fixture
def settings_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "settings-test-" + "x" * 48)
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-key-should-not-appear")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "gpt-test")
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def override_db() -> Generator[Session, None, None]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with Session(engine) as db:
        own = Workspace(slug="settings-own", name="配置工作区")
        other = Workspace(slug="settings-other", name="其他工作区")
        admin = User(
            email="admin-settings@example.com",
            display_name="管理员",
            password_hash=hash_password("test-password-123"),
        )
        operator = User(
            email="operator-settings@example.com",
            display_name="运营人员",
            password_hash=hash_password("test-password-123"),
        )
        db.add_all([own, other, admin, operator])
        db.flush()
        store = Store(workspace_id=own.id, name="配置测试店铺", platform="抖音")
        db.add_all(
            [
                WorkspaceMembership(workspace_id=own.id, user_id=admin.id, role="admin"),
                WorkspaceMembership(workspace_id=own.id, user_id=operator.id, role="operator"),
                store,
            ]
        )
        db.commit()
        admin_headers = {
            "Authorization": f"Bearer {create_access_token(admin)}",
            "X-Workspace-ID": str(own.id),
        }
        operator_headers = {
            "Authorization": f"Bearer {create_access_token(operator)}",
            "X-Workspace-ID": str(own.id),
        }
        store_id, other_id = store.id, other.id
    try:
        yield TestClient(app), engine, admin_headers, operator_headers, store_id, other_id
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def test_admin_settings_persistence_audit_and_secret_boundary(settings_client) -> None:
    client, engine, admin, operator, store_id, other_id = settings_client
    url = "/api/v1/settings"
    initial = client.get(url, headers=admin)
    assert initial.status_code == 200
    assert initial.json()["services"][0]["has_api_key"] is True
    assert initial.json()["services"][0]["model"] == "gpt-test"
    assert "test-secret-key-should-not-appear" not in initial.text
    assert client.get(url, headers=operator).status_code == 403
    assert client.get(url, headers={**admin, "X-Workspace-ID": str(other_id)}).status_code == 403

    changed = client.patch(
        f"{url}/services/text", json={"provider": "openai", "model": "gpt-other"}, headers=admin
    )
    assert changed.status_code == 200
    assert changed.json()["services"][0]["model"] == "gpt-other"
    assert (
        client.patch(
            f"{url}/services/text",
            json={"provider": "openai", "model": "x", "api_key": "leak"},
            headers=admin,
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{url}/services/text", json={"provider": "jimeng", "model": "x"}, headers=admin
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{url}/services/text", json={"provider": "openai", "model": "x"}, headers=operator
        ).status_code
        == 403
    )

    rules = {
        "timeout_seconds": 420,
        "max_retries": 4,
        "max_concurrency": 3,
        "image_poll_interval_seconds": 8,
        "image_poll_max_attempts": 30,
        "video_poll_interval_seconds": 15,
        "video_poll_max_attempts": 25,
    }
    assert client.put(f"{url}/rules", json=rules, headers=admin).status_code == 200
    assert client.put(f"{url}/rules", json=rules, headers=operator).status_code == 403
    assert client.get(url, headers=admin).json()["rules"] == rules

    platform = client.patch(
        f"{url}/platform-accounts/{store_id}",
        json={"account_identifier": "douyin-shop-001", "authorization_status": "placeholder"},
        headers=admin,
    )
    assert platform.status_code == 200
    assert platform.json()["authorization_status"] == "placeholder"
    assert (
        client.patch(
            f"{url}/platform-accounts/{store_id}",
            json={
                "account_identifier": "x",
                "authorization_status": "placeholder",
                "cookie": "leak",
            },
            headers=admin,
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{url}/platform-accounts/{store_id}",
            json={"account_identifier": "x", "authorization_status": "placeholder"},
            headers=operator,
        ).status_code
        == 403
    )
    with Session(engine) as db:
        assert (
            db.scalar(
                select(PlatformAccountPlaceholder).where(
                    PlatformAccountPlaceholder.store_id == store_id
                )
            ).account_identifier
            == "douyin-shop-001"
        )
        events = list(db.scalars(select(AuditEvent).where(AuditEvent.action.like("settings.%"))))
        assert len(events) == 3
        assert "test-secret-key-should-not-appear" not in str([event.details for event in events])
    assert len(client.get(f"{url}/audit", headers=admin).json()) == 3


def test_connection_check_reports_real_probe_result_without_leaking_secret(
    settings_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, admin, _, _, _ = settings_client

    class Success:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.services.service_settings.urlopen", lambda request, timeout: Success())
    success = client.post("/api/v1/settings/services/text/check", headers=admin)
    assert success.status_code == 200
    assert success.json()["ok"] is True
    assert "test-secret-key-should-not-appear" not in success.text

    def reject(request, timeout):
        raise HTTPError(request.full_url, 401, "secret error detail", {}, None)

    monkeypatch.setattr("app.services.service_settings.urlopen", reject)
    failed = client.post("/api/v1/settings/services/text/check", headers=admin)
    assert failed.status_code == 200
    assert failed.json()["code"] == "authorization_failed"
    assert "secret error detail" not in failed.text
    video = client.post("/api/v1/settings/services/video/check", headers=admin)
    assert video.json()["code"] == "not_configured"


def test_missing_environment_key_never_counts_as_connection(
    settings_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, admin, _, _, _ = settings_client
    monkeypatch.delenv("OPENAI_API_KEY")
    get_settings.cache_clear()
    response = client.get("/api/v1/settings", headers=admin)
    assert response.status_code == 200
    assert response.json()["services"][0]["has_api_key"] is False
    assert response.json()["services"][0]["configured"] is False
    check = client.post("/api/v1/settings/services/text/check", headers=admin)
    assert check.json()["ok"] is False
    assert check.json()["code"] == "not_configured"
