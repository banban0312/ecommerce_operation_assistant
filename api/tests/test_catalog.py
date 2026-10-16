"""M2 商品主数据、库存流水和工作空间隔离验收。"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models import Base, User, Workspace, WorkspaceMembership
from app.services.auth import create_access_token
from app.services.users import hash_password


@pytest.fixture
def catalog_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "catalog-test-" + "x" * 48)
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
        own, other = (
            Workspace(slug="own", name="当前工作区"),
            Workspace(slug="other", name="其他工作区"),
        )
        user = User(
            email="operator@example.com",
            display_name="运营人员",
            password_hash=hash_password("long-test-password"),
        )
        db.add_all([own, other, user])
        db.flush()
        db.add(WorkspaceMembership(workspace_id=own.id, user_id=user.id, role="operator"))
        db.commit()
        token = create_access_token(user)
        own_id, other_id = own.id, other.id
    try:
        yield (
            TestClient(app),
            {"Authorization": f"Bearer {token}", "X-Workspace-ID": str(own_id)},
            other_id,
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def test_catalog_inventory_competitor_and_product_isolation(catalog_client) -> None:
    client, headers, _ = catalog_client
    store = client.post(
        "/api/v1/catalog/stores", json={"name": "旗舰店", "platform": "抖音"}, headers=headers
    )
    assert store.status_code == 201
    store_id = store.json()["id"]
    product = client.post(
        "/api/v1/catalog/products",
        json={"store_id": store_id, "name": "夏季防晒衣", "category": "服装"},
        headers=headers,
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    sku_ids = []
    for code, spec, price, stock in [
        ("WHITE-M", "白色 M", "99.00", 20),
        ("BLACK-L", "黑色 L", "109.00", 12),
    ]:
        response = client.post(
            f"/api/v1/catalog/products/{product_id}/skus",
            json={
                "sku_code": code,
                "specification": spec,
                "price": price,
                "stock": stock,
                "warning_threshold": 5,
            },
            headers=headers,
        )
        assert response.status_code == 201
        sku_ids.append(response.json()["id"])
    skus = client.get(f"/api/v1/catalog/products/{product_id}/skus", headers=headers).json()
    assert [sku["specification"] for sku in skus] == ["白色 M", "黑色 L"]
    assert [sku["price"] for sku in skus] == ["99.00", "109.00"]

    adjusted = client.post(
        f"/api/v1/catalog/products/{product_id}/skus/{sku_ids[0]}/inventory",
        json={"quantity": 3, "reason": "盘点调整"},
        headers=headers,
    )
    assert adjusted.status_code == 201
    assert adjusted.json()["delta"] == -17
    movements = client.get(
        f"/api/v1/catalog/products/{product_id}/inventory-movements", headers=headers
    ).json()
    assert [item["reason"] for item in movements] == ["盘点调整", "初始库存", "初始库存"]
    summary = client.get("/api/v1/catalog/dashboard", headers=headers).json()
    assert summary["warning_count"] == 1
    assert summary["warnings"][0]["product_id"] == product_id

    competitor = client.post(
        f"/api/v1/catalog/products/{product_id}/competitors",
        json={
            "name": "竞品 A",
            "price": "89.50",
            "attributes": {"面料": "锦纶", "防晒指数": "UPF50+"},
        },
        headers=headers,
    )
    assert competitor.status_code == 201
    assert (
        client.get(f"/api/v1/catalog/products/{product_id}/competitors", headers=headers).json()[0][
            "attributes"
        ]["面料"]
        == "锦纶"
    )

    second = client.post(
        "/api/v1/catalog/products", json={"store_id": store_id, "name": "另一商品"}, headers=headers
    ).json()
    second_id = second["id"]
    assert client.get(f"/api/v1/catalog/products/{second_id}/skus", headers=headers).json() == []
    assert (
        client.get(f"/api/v1/catalog/products/{second_id}/competitors", headers=headers).json()
        == []
    )
    assert (
        client.get(
            f"/api/v1/catalog/products/{second_id}/inventory-movements", headers=headers
        ).json()
        == []
    )
    assert client.get("/api/v1/catalog/products?q=夏季", headers=headers).json()["total"] == 1
    # 商品池按 SKU 搜索时仍以商品分页，不能因多个规格重复计数。
    sku_result = client.get("/api/v1/catalog/products?q=WHITE", headers=headers).json()
    assert sku_result["total"] == 1
    assert sku_result["items"][0]["sku_count"] == 2
    assert sku_result["items"][0]["price_min"] == "99.00"
    assert sku_result["items"][0]["price_max"] == "109.00"
    assert sku_result["items"][0]["has_stock_warning"] is True
    assert (
        client.get("/api/v1/catalog/products?stock_status=warning", headers=headers).json()["total"]
        == 1
    )
    assert (
        client.get("/api/v1/catalog/products?stock_status=no_sku", headers=headers).json()["total"]
        == 1
    )
    assert (
        client.get("/api/v1/catalog/products?platform=抖音", headers=headers).json()["total"] == 2
    )
    profile = client.patch(
        f"/api/v1/catalog/products/{product_id}",
        json={
            "platform_item_code": "DY-001",
            "cost": "36.50",
            "target_audience": "通勤女性",
            "selling_points": "轻薄防晒",
        },
        headers=headers,
    )
    assert profile.status_code == 200
    assert profile.json()["cost"] == "36.50"
    assert (
        client.get("/api/v1/catalog/products?profile_incomplete=true", headers=headers).json()[
            "total"
        ]
        == 1
    )
    assert (
        client.get("/api/v1/catalog/products?page=2&page_size=1", headers=headers).json()["items"][
            0
        ]["id"]
        == product_id
    )


def test_workspace_boundary_and_conflicting_sku(catalog_client) -> None:
    client, headers, other_id = catalog_client
    own_store = client.post(
        "/api/v1/catalog/stores", json={"name": "本店", "platform": "淘宝"}, headers=headers
    ).json()
    product = client.post(
        "/api/v1/catalog/products",
        json={"store_id": own_store["id"], "name": "商品"},
        headers=headers,
    ).json()
    body = {"sku_code": "ONE", "specification": "一号", "price": "10.00"}
    assert (
        client.post(
            f"/api/v1/catalog/products/{product['id']}/skus", json=body, headers=headers
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/v1/catalog/products/{product['id']}/skus", json=body, headers=headers
        ).status_code
        == 409
    )
    foreign_headers = {**headers, "X-Workspace-ID": str(other_id)}
    assert client.get("/api/v1/catalog/products", headers=foreign_headers).status_code == 403
    assert (
        client.get(f"/api/v1/catalog/products/{product['id']}", headers=foreign_headers).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/catalog/products",
            json={"store_id": own_store["id"], "name": "越权商品"},
            headers=foreign_headers,
        ).status_code
        == 403
    )
