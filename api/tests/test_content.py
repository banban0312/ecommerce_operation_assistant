"""M4 内容生成、编辑、确认和乐观锁验收。"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models import Base, Product, Store, User, Workspace, WorkspaceMembership
from app.services.auth import create_access_token
from app.services.users import hash_password


@pytest.fixture
def content_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "content-test-" + "x" * 48)
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
        workspace = Workspace(slug="content-workspace", name="内容工作区")
        user = User(
            email="content@example.com",
            display_name="管理员",
            password_hash=hash_password("password-123"),
        )
        db.add_all([workspace, user])
        db.flush()
        store = Store(workspace_id=workspace.id, name="内容店铺", platform="抖音")
        db.add_all(
            [store, WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="admin")]
        )
        db.flush()
        product = Product(
            store_id=store.id,
            name="防晒衣",
            category="服装",
            target_audience="通勤女性",
            selling_points="轻薄防晒",
        )
        db.add(product)
        db.commit()
        headers = {
            "Authorization": f"Bearer {create_access_token(user)}",
            "X-Workspace-ID": str(workspace.id),
        }
        product_id = product.id
    with TestClient(app) as client:
        yield client, headers, product_id
    app.dependency_overrides.clear()


def fake_model(prompt: str, **_: object) -> dict:
    if "diagnosis" in prompt:
        return {
            "target_audience": "通勤女性",
            "price_band": "100-200",
            "selling_point_matrix": [{"point": "轻薄", "evidence": "档案"}],
            "conversion_blockers": ["缺少场景证明"],
            "optimization_directions": ["补充通勤场景"],
        }
    if "image_ideas" in prompt:
        return {
            "items": [
                {
                    "title": f"主图方向 {i}",
                    "layout": "左文右图",
                    "copy": "轻薄防晒",
                    "selling_point": "轻薄",
                    "visual_guidance": "自然光",
                }
                for i in range(1, 4)
            ]
        }
    return {
        "items": [
            {
                "title": f"脚本 {i}",
                "hook_3s": "出门怕晒？",
                "shots": [{"scene": "通勤", "voiceover": "轻薄防晒"}],
                "call_to_action": "立即了解",
            }
            for i in range(1, 4)
        ]
    }


def test_generation_edit_confirm_and_conflict(
    content_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, headers, product_id = content_client
    monkeypatch.setattr("app.api.routes.content.request_structured", fake_model)
    base = f"/api/v1/content/products/{product_id}"
    diagnosis = client.post(f"{base}/diagnosis", headers=headers)
    assert diagnosis.status_code == 200
    assert len(client.post(f"{base}/image-ideas", headers=headers).json()["items"]) == 3
    assert len(client.post(f"{base}/video-scripts", headers=headers).json()["items"]) == 3
    item = diagnosis.json()["items"][0]
    edited = client.patch(
        f"/api/v1/content/{item['id']}",
        headers=headers,
        json={"revision": 1, "content": {"target_audience": "新客群"}},
    )
    assert edited.status_code == 200
    assert (
        client.patch(
            f"/api/v1/content/{item['id']}",
            headers=headers,
            json={"revision": 1, "content": {"target_audience": "旧页面"}},
        ).status_code
        == 409
    )
    confirmed = client.post(f"/api/v1/content/{item['id']}/confirm", headers=headers)
    assert confirmed.status_code == 200
    assert (
        client.patch(
            f"/api/v1/content/{item['id']}",
            headers=headers,
            json={"revision": 2, "content": {"target_audience": "覆盖"}},
        ).status_code
        == 409
    )
    regenerated = client.post(f"{base}/diagnosis", headers=headers)
    assert regenerated.status_code == 200
    diagnoses = client.get(base, headers=headers).json()["diagnosis"]
    assert len(diagnoses) == 2
    assert {item["status"] for item in diagnoses} == {"confirmed", "draft"}
