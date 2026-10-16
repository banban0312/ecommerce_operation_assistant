"""M12 素材筛选、商品归属和版本比较验收。"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models import (
    Base,
    GenerationJob,
    MediaAsset,
    Product,
    Store,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.services.auth import create_access_token
from app.services.users import hash_password


@pytest.fixture
def media_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "m12-test-" + "x" * 48)
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
        workspace = Workspace(slug="m12", name="M12 工作区")
        user = User(
            email="m12@example.com",
            display_name="管理员",
            password_hash=hash_password("long-test-password"),
        )
        db.add_all([workspace, user])
        db.flush()
        db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="admin"))
        store = Store(workspace_id=workspace.id, name="演示店", platform="淘宝")
        db.add(store)
        db.flush()
        product = Product(store_id=store.id, name="无线充演示商品")
        db.add(product)
        db.flush()
        for number, media_type, tags in [(1, "image", ["主图", "对比"]), (2, "video", ["短视频"])]:
            job = GenerationJob(
                workspace_id=workspace.id,
                product_id=product.id,
                content_version_id=1,
                media_type=media_type,
                idempotency_key=f"m12-{number}-long",
                created_by=user.id,
                status="succeeded",
            )
            db.add(job)
            db.flush()
            db.add(
                MediaAsset(
                    workspace_id=workspace.id,
                    product_id=product.id,
                    job_id=job.id,
                    content_version_id=1,
                    media_type=media_type,
                    storage_path=f"demo/{number}.bin",
                    review_status="approved" if number == 1 else "pending",
                    tags=tags,
                    updated_by=user.id,
                )
            )
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


def test_media_filters_and_compare_stay_within_product(media_client) -> None:
    client, headers, product_id = media_client
    filtered = client.get(
        f"/api/v1/media/products/{product_id}/assets?media_type=image&review_status=approved&tag=主图",
        headers=headers,
    )
    assert filtered.status_code == 200 and len(filtered.json()) == 1
    ids = [
        item["id"]
        for item in client.get(
            f"/api/v1/media/products/{product_id}/assets", headers=headers
        ).json()
    ]
    compared = client.get(
        f"/api/v1/media/products/{product_id}/assets/compare?asset_ids={ids[0]},{ids[1]}",
        headers=headers,
    )
    assert compared.status_code == 200
    assert compared.json()["product_id"] == product_id
