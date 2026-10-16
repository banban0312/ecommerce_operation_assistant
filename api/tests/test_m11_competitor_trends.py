"""M11 竞品来源解析、工作区隔离和经营趋势验收。"""

from collections.abc import Generator
from datetime import date

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
def m11_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "m11-test-" + "x" * 48)
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
        workspace = Workspace(slug="m11", name="M11 工作区")
        user = User(
            email="m11@example.com",
            display_name="运营",
            password_hash=hash_password("long-test-password"),
        )
        db.add_all([workspace, user])
        db.flush()
        db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="operator"))
        store = Store(workspace_id=workspace.id, name="旗舰店", platform="淘宝")
        db.add(store)
        db.flush()
        product = Product(store_id=store.id, name="防晒衣")
        db.add(product)
        db.commit()
        token, workspace_id, product_id = create_access_token(user), workspace.id, product.id
    try:
        yield (
            TestClient(app),
            {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(workspace_id)},
            product_id,
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def test_competitor_link_parser_preserves_manual_fallback(m11_client) -> None:
    client, headers, product_id = m11_client
    parsed = client.post(
        f"/api/v1/catalog/products/{product_id}/competitors/parse",
        json={"source_url": "https://item.taobao.com/item.htm?name=竞品&price=89.5"},
        headers=headers,
    )
    assert parsed.status_code == 200
    assert parsed.json()["status"] == "parsed"
    unsupported = client.post(
        f"/api/v1/catalog/products/{product_id}/competitors/parse",
        json={"source_url": "https://example.com/item/1"},
        headers=headers,
    )
    assert unsupported.json()["status"] == "manual_required"


def test_trends_returns_real_periods_without_zero_filling(m11_client) -> None:
    client, headers, product_id = m11_client
    body = {
        "period_start": date(2026, 1, 1).isoformat(),
        "period_end": date(2026, 1, 31).isoformat(),
        "source": "manual",
        "target_gmv": "1000",
        "actual_gmv": "1200",
        "target_impressions": 100,
        "actual_impressions": 120,
        "target_ctr": "0.1",
        "actual_ctr": "0.12",
        "target_conversion_rate": "0.05",
        "actual_conversion_rate": "0.06",
        "target_roi": "2",
        "actual_roi": "2.4",
    }
    assert (
        client.post(
            f"/api/v1/review/products/{product_id}/metrics", json=body, headers=headers
        ).status_code
        == 201
    )
    response = client.get("/api/v1/catalog/trends", headers=headers)
    assert response.status_code == 200
    assert len(response.json()["series"][0]["points"]) == 1
    assert response.json()["series"][0]["points"][0]["actual_gmv"] == "1200.00"
