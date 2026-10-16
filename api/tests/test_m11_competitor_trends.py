"""M11 竞品来源解析、工作区隔离和经营趋势验收。"""

from collections.abc import Generator
from datetime import date
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
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
        db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="supervisor"))
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
    saved = client.post(
        f"/api/v1/catalog/products/{product_id}/competitors",
        json={
            "name": "竞品",
            "price": "89.50",
            "source_url": "https://item.taobao.com/item.htm?name=竞品&price=89.5",
        },
        headers=headers,
    )
    assert saved.status_code == 201
    assert saved.json()["source_status"] == "parsed"
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


def test_demo_seed_populates_overview_and_is_idempotent(m11_client) -> None:
    client, headers, _ = m11_client

    first = client.post("/api/v1/catalog/demo/wireless-charger", headers=headers)
    assert first.status_code == 201
    body = first.json()
    assert body["label"] == "模拟/演示数据"
    assert len(body["included"]) >= 5

    dashboard = client.get("/api/v1/catalog/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["store_count"] == 3
    assert dashboard.json()["product_count"] == 3
    assert dashboard.json()["warning_count"] == 1

    trends = client.get("/api/v1/catalog/trends", headers=headers)
    assert trends.status_code == 200
    assert sum(len(series["points"]) for series in trends.json()["series"]) == 7
    batches = client.get("/api/v1/imports/batches", headers=headers)
    assert batches.status_code == 200
    demo_batch = next(
        item for item in batches.json() if item["filename"] == "wireless-charger-demo.csv"
    )
    assert demo_batch["status"] == "preview"
    assert (demo_batch["valid_count"], demo_batch["error_count"]) == (1, 1)

    second = client.post("/api/v1/catalog/demo/wireless-charger", headers=headers)
    assert second.status_code == 201
    assert second.json()["product_id"] == body["product_id"]
    assert second.json()["included"] == body["included"]
    assert client.get("/api/v1/catalog/dashboard", headers=headers).json() == dashboard.json()
    assert client.get("/api/v1/catalog/trends", headers=headers).json() == trends.json()
    repeated_batches = client.get("/api/v1/imports/batches", headers=headers).json()
    assert sum(item["filename"] == "wireless-charger-demo.csv" for item in repeated_batches) == 1


def test_import_templates_support_csv_and_xlsx(m11_client) -> None:
    client, headers, _ = m11_client
    expected = [
        "store_id", "name", "category", "description", "platform_item_code",
        "cost", "target_audience", "selling_points",
    ]

    csv_template = client.get(
        "/api/v1/imports/templates/products?file_format=csv", headers=headers
    )
    assert csv_template.status_code == 200
    assert csv_template.headers["content-disposition"].endswith('products-template.csv"')
    assert csv_template.content.decode("utf-8-sig").strip().split(",") == expected

    xlsx_template = client.get(
        "/api/v1/imports/templates/products?file_format=xlsx", headers=headers
    )
    assert xlsx_template.status_code == 200
    assert xlsx_template.headers["content-disposition"].endswith('products-template.xlsx"')
    sheet = load_workbook(BytesIO(xlsx_template.content), read_only=True).active
    assert list(next(sheet.values)) == expected
    assert client.get(
        "/api/v1/imports/templates/products?file_format=doc", headers=headers
    ).status_code == 422


def test_import_preview_rejects_empty_or_mismatched_template(m11_client) -> None:
    client, headers, _ = m11_client
    empty = client.post(
        "/api/v1/imports/preview?data_type=products",
        files={"file": ("products.csv", b"store_id,name\n")},
        headers=headers,
    )
    assert empty.status_code == 422
    assert "表头与products模板不匹配" in empty.json()["message"]

    no_rows = client.post(
        "/api/v1/imports/preview?data_type=products",
        files={
            "file": (
                "products.csv",
                b"store_id,name,category,description,platform_item_code,cost,target_audience,selling_points\n",
            )
        },
        headers=headers,
    )
    assert no_rows.status_code == 422
    assert "没有可导入的数据行" in no_rows.json()["message"]


def test_import_preview_keeps_source_line_numbers_and_flags_extra_columns(m11_client) -> None:
    client, headers, _ = m11_client
    csv_content = (
        "store_id,name,category,description,platform_item_code,cost,target_audience,selling_points\n"
        "1,防晒衣,服装,春夏款,,100,通勤,轻薄\n"
        "\n"
        "1,帽子,服装,遮阳帽,,20,户外,透气,unexpected\n"
    ).encode()
    response = client.post(
        "/api/v1/imports/preview?data_type=products",
        files={"file": ("products.csv", csv_content)},
        headers=headers,
    )

    assert response.status_code == 201
    rows = response.json()["rows"]
    assert [row["line"] for row in rows] == [2, 4]
    assert rows[0]["valid"] is True
    assert rows[1]["valid"] is False
    assert "额外列数据" in rows[1]["errors"][0]
