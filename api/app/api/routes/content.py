"""商品诊断、创意和脚本 API；每个版本绑定商品并受工作空间权限保护。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select

from app.api.dependencies import SessionDep, get_workspace_access
from app.models import Competitor, ContentVersion, Product, ProductSku, ServiceConfig, Store
from app.schemas.content import ContentBundle, ContentRead, ContentUpdate, GenerationRead
from app.services.audit import record_audit_event
from app.services.text_provider import build_prompt, request_structured
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/content", tags=["content"])
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]


def _product(db: SessionDep, access: WorkspaceAccess, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    store = db.get(Store, product.store_id)
    if store is None or store.workspace_id != access.workspace.id:
        raise HTTPException(status_code=403, detail="无权访问此商品")
    return product


def _read(row: ContentVersion) -> ContentRead:
    return ContentRead.model_validate(row, from_attributes=True)


def _bundle(db: SessionDep, product_id: int) -> ContentBundle:
    rows = list(
        db.scalars(
            select(ContentVersion)
            .where(ContentVersion.product_id == product_id, ContentVersion.status != "archived")
            .order_by(
                ContentVersion.content_type,
                ContentVersion.slot_key,
                desc(ContentVersion.version_no),
            )
        )
    )
    selected: list[ContentVersion] = []
    grouped: dict[tuple[str, str], list[ContentVersion]] = {}
    for row in rows:
        grouped.setdefault((row.content_type, row.slot_key), []).append(row)
    for versions in grouped.values():
        # 已确认版本全部保留，另展示该槽位最新的可编辑草稿。
        selected.extend(row for row in versions if row.status == "confirmed")
        draft = next((row for row in versions if row.status != "confirmed"), None)
        if draft is not None:
            selected.append(draft)
    return ContentBundle(
        product_id=product_id,
        diagnosis=[_read(row) for row in selected if row.content_type == "diagnosis"],
        image_ideas=[_read(row) for row in selected if row.content_type == "image_idea"],
        video_scripts=[_read(row) for row in selected if row.content_type == "video_script"],
    )


def _context(db: SessionDep, product: Product) -> tuple[dict, list[dict], list[dict]]:
    skus = db.scalars(
        select(ProductSku).where(ProductSku.product_id == product.id, ProductSku.status == "active")
    ).all()
    competitors = db.scalars(select(Competitor).where(Competitor.product_id == product.id)).all()
    return (
        {
            "name": product.name,
            "category": product.category,
            "description": product.description,
            "target_audience": product.target_audience,
            "selling_points": product.selling_points,
            "cost": str(product.cost) if product.cost is not None else None,
        },
        [
            {
                "sku_code": sku.sku_code,
                "specification": sku.specification,
                "price": str(sku.price),
                "stock": sku.stock,
            }
            for sku in skus
        ],
        [
            {"name": item.name, "price": str(item.price), "attributes": item.attributes}
            for item in competitors
        ],
    )


def _ensure_ready(db: SessionDep, product: Product) -> None:
    if not product.target_audience.strip() or not product.selling_points.strip():
        raise HTTPException(status_code=422, detail="请先完善目标人群和核心卖点，再生成诊断或创意")


def _text_model(db: SessionDep, access: WorkspaceAccess) -> str | None:
    """M3 页面保存的非敏感模型名优先于环境默认值。"""
    row = db.scalar(
        select(ServiceConfig).where(
            ServiceConfig.workspace_id == access.workspace.id,
            ServiceConfig.target == "text",
        )
    )
    return row.model if row and row.model else None


def _next_version(db: SessionDep, product_id: int, content_type: str, slot: str) -> int:
    value = db.scalar(
        select(func.max(ContentVersion.version_no)).where(
            ContentVersion.product_id == product_id,
            ContentVersion.content_type == content_type,
            ContentVersion.slot_key == slot,
        )
    )
    return (value or 0) + 1


def _save(
    db: SessionDep,
    access: WorkspaceAccess,
    product_id: int,
    content_type: str,
    slot: str,
    content: dict,
) -> ContentVersion:
    row = ContentVersion(
        product_id=product_id,
        content_type=content_type,
        slot_key=slot,
        version_no=_next_version(db, product_id, content_type, slot),
        content=content,
        updated_by=access.user.id,
    )
    db.add(row)
    record_audit_event(
        db,
        access=access,
        action="content.generated",
        resource_type=content_type,
        resource_id=str(product_id),
        details={"slot": slot, "version": row.version_no},
    )
    return row


@router.get("/products/{product_id}", response_model=ContentBundle)
def list_content(product_id: int, db: SessionDep, access: Access) -> ContentBundle:
    _product(db, access, product_id)
    return _bundle(db, product_id)


@router.post("/products/{product_id}/diagnosis", response_model=GenerationRead)
def generate_diagnosis(product_id: int, db: SessionDep, access: Access) -> GenerationRead:
    product = _product(db, access, product_id)
    _ensure_ready(db, product)
    p, skus, competitors = _context(db, product)
    data = request_structured(
        build_prompt(p, skus, competitors, "diagnosis"), model=_text_model(db, access)
    )
    required = {
        "target_audience",
        "price_band",
        "selling_point_matrix",
        "conversion_blockers",
        "optimization_directions",
    }
    if not required.issubset(data) or not isinstance(data["selling_point_matrix"], list):
        raise HTTPException(status_code=502, detail="模型诊断结构不完整，请稍后重试")
    row = _save(db, access, product_id, "diagnosis", "default", data)
    db.commit()
    db.refresh(row)
    return GenerationRead(message="诊断草稿已生成，可继续编辑后确认。", items=[_read(row)])


def _generate_many(
    product_id: int,
    db: SessionDep,
    access: WorkspaceAccess,
    output: str,
    content_type: str,
    message: str,
) -> GenerationRead:
    product = _product(db, access, product_id)
    _ensure_ready(db, product)
    p, skus, competitors = _context(db, product)
    data = request_structured(
        build_prompt(p, skus, competitors, output), model=_text_model(db, access)
    )
    items = data.get("items")
    if (
        not isinstance(items, list)
        or len(items) < 3
        or not all(isinstance(item, dict) for item in items[:3])
    ):
        raise HTTPException(status_code=502, detail="模型返回内容数量或结构不完整，请稍后重试")
    rows = [
        _save(db, access, product_id, content_type, str(index + 1), item)
        for index, item in enumerate(items[:3])
    ]
    db.commit()
    for row in rows:
        db.refresh(row)
    return GenerationRead(message=message, items=[_read(row) for row in rows])


@router.post("/products/{product_id}/image-ideas", response_model=GenerationRead)
def generate_image_ideas(product_id: int, db: SessionDep, access: Access) -> GenerationRead:
    return _generate_many(
        product_id,
        db,
        access,
        "image_ideas",
        "image_idea",
        "已生成 3 组主图创意草稿，可逐项编辑和确认。",
    )


@router.post("/products/{product_id}/video-scripts", response_model=GenerationRead)
def generate_video_scripts(product_id: int, db: SessionDep, access: Access) -> GenerationRead:
    return _generate_many(
        product_id,
        db,
        access,
        "video_scripts",
        "video_script",
        "已生成 3 套视频脚本草稿，可逐项编辑和确认。",
    )


@router.patch("/{content_id}", response_model=ContentRead)
def update_content(
    content_id: int, payload: ContentUpdate, db: SessionDep, access: Access
) -> ContentRead:
    row = db.get(ContentVersion, content_id)
    if row is None:
        raise HTTPException(status_code=404, detail="内容版本不存在")
    _product(db, access, row.product_id)
    if row.revision != payload.revision:
        raise HTTPException(status_code=409, detail="内容已被其他页面修改，请刷新后重试")
    if row.status == "confirmed":
        raise HTTPException(status_code=409, detail="已确认版本不可直接覆盖，请重新生成新版本")
    row.content = payload.content
    row.revision += 1
    row.source = "human"
    row.updated_by = access.user.id
    record_audit_event(
        db,
        access=access,
        action="content.edited",
        resource_type=row.content_type,
        resource_id=str(row.id),
        details={"revision": row.revision},
    )
    db.commit()
    db.refresh(row)
    return _read(row)


@router.post("/{content_id}/confirm", response_model=ContentRead)
def confirm_content(content_id: int, db: SessionDep, access: Access) -> ContentRead:
    row = db.get(ContentVersion, content_id)
    if row is None:
        raise HTTPException(status_code=404, detail="内容版本不存在")
    _product(db, access, row.product_id)
    if row.status == "archived":
        raise HTTPException(status_code=409, detail="已归档版本不能确认")
    row.status = "confirmed"
    row.updated_by = access.user.id
    record_audit_event(
        db,
        access=access,
        action="content.confirmed",
        resource_type=row.content_type,
        resource_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    return _read(row)


@router.post("/{content_id}/archive", response_model=ContentRead)
def archive_content(content_id: int, db: SessionDep, access: Access) -> ContentRead:
    row = db.get(ContentVersion, content_id)
    if row is None:
        raise HTTPException(status_code=404, detail="内容版本不存在")
    _product(db, access, row.product_id)
    row.status = "archived"
    row.updated_by = access.user.id
    record_audit_event(
        db,
        access=access,
        action="content.archived",
        resource_type=row.content_type,
        resource_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    return _read(row)
