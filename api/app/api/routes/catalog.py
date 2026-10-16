"""店铺、商品、SKU、库存和竞品接口；所有资源都先校验工作空间归属。"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import SessionDep, get_workspace_access, require_roles
from app.models import (
    AdProposal,
    AgentApproval,
    AgentStep,
    AgentTask,
    BusinessMetric,
    Competitor,
    ContentVersion,
    GenerationEvent,
    GenerationJob,
    ImportBatch,
    InventoryMovement,
    MediaAsset,
    Product,
    ProductSku,
    ReviewReport,
    Store,
    WorkspaceRole,
)
from app.schemas.catalog import (
    CompetitorCreate,
    CompetitorParse,
    CompetitorParseRead,
    CompetitorRead,
    CompetitorUpdate,
    DashboardSummary,
    DemoSeedRead,
    InventoryAdjust,
    InventoryMovementRead,
    ProductCreate,
    ProductList,
    ProductListItem,
    ProductRead,
    ProductTrendRead,
    ProductUpdate,
    SkuCreate,
    SkuRead,
    SkuUpdate,
    StockWarning,
    StoreCreate,
    StoreRead,
    StoreUpdate,
    TrendPoint,
    TrendsRead,
)
from app.services.audit import record_audit_event
from app.services.workspaces import WorkspaceAccess

router = APIRouter(prefix="/catalog", tags=["catalog"])
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]


def _commit(db: SessionDep) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="记录冲突，请检查编号或关联数据") from exc


def _store(db: SessionDep, access: WorkspaceAccess, store_id: int) -> Store:
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="店铺不存在")
    if store.workspace_id != access.workspace.id:
        raise HTTPException(status_code=403, detail="无权访问此店铺")
    return store


def _product(db: SessionDep, access: WorkspaceAccess, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    _store(db, access, product.store_id)
    return product


def _sku(db: SessionDep, product_id: int, sku_id: int, *, lock: bool = False) -> ProductSku:
    statement = select(ProductSku).where(
        ProductSku.id == sku_id, ProductSku.product_id == product_id
    )
    if lock:
        # MySQL 行锁使并发库存调整按顺序计算，不丢失流水或覆盖更新。
        statement = statement.with_for_update()
    sku = db.scalar(statement)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU 不属于当前商品")
    return sku


@router.get("/stores", response_model=list[StoreRead])
def list_stores(db: SessionDep, access: Access) -> list[StoreRead]:
    stores = list(
        db.scalars(
            select(Store)
            .where(Store.workspace_id == access.workspace.id, Store.status == "active")
            .order_by(Store.id.desc())
        )
    )
    counts = (
        dict(
            db.execute(
                select(Product.store_id, func.count(Product.id))
                .where(
                    Product.store_id.in_([store.id for store in stores]), Product.status == "active"
                )
                .group_by(Product.store_id)
            ).all()
        )
        if stores
        else {}
    )
    return [
        StoreRead.model_validate(store).model_copy(
            update={"product_count": counts.get(store.id, 0)}
        )
        for store in stores
    ]


@router.post("/stores", response_model=StoreRead, status_code=status.HTTP_201_CREATED)
def create_store(payload: StoreCreate, db: SessionDep, access: Access) -> Store:
    store = Store(
        workspace_id=access.workspace.id,
        name=payload.name.strip(),
        platform=payload.platform.strip(),
    )
    if not store.name or not store.platform:
        raise HTTPException(status_code=422, detail="店铺名称和平台不能为空")
    db.add(store)
    _commit(db)
    db.refresh(store)
    return store


@router.get("/stores/{store_id}", response_model=StoreRead)
def get_store(store_id: int, db: SessionDep, access: Access) -> Store:
    return _store(db, access, store_id)


@router.patch("/stores/{store_id}", response_model=StoreRead)
def update_store(store_id: int, payload: StoreUpdate, db: SessionDep, access: Access) -> Store:
    store = _store(db, access, store_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None or (isinstance(value, str) and not value.strip()):
            raise HTTPException(status_code=422, detail="店铺字段不能为空")
        setattr(store, field, value.strip() if isinstance(value, str) else value)
    _commit(db)
    db.refresh(store)
    return store


@router.delete("/stores/{store_id}", status_code=204)
def archive_store(store_id: int, db: SessionDep, access: Access) -> None:
    # 归档保留商品、库存与竞品历史，避免硬删除破坏审计。
    _store(db, access, store_id).status = "archived"
    _commit(db)


@router.get("/products", response_model=ProductList)
def list_products(
    db: SessionDep,
    access: Access,
    store_id: int | None = None,
    q: str = "",
    platform: str = "",
    stock_status: str = "",
    profile_incomplete: bool = False,
    sort: str = "newest",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductList:
    if store_id is not None:
        _store(db, access, store_id)
    condition = [
        Store.workspace_id == access.workspace.id,
        Store.status == "active",
        Product.status == "active",
    ]
    if store_id is not None:
        condition.append(Product.store_id == store_id)
    if platform.strip():
        condition.append(Store.platform == platform.strip())
    if q.strip():
        pattern = f"%{q.strip()}%"
        sku_match = (
            select(ProductSku.id)
            .where(
                ProductSku.product_id == Product.id,
                ProductSku.status == "active",
                ProductSku.sku_code.ilike(pattern),
            )
            .exists()
        )
        condition.append(or_(Product.name.ilike(pattern), sku_match))
    warning = (
        select(ProductSku.id)
        .where(
            ProductSku.product_id == Product.id,
            ProductSku.status == "active",
            ProductSku.stock < ProductSku.warning_threshold,
        )
        .exists()
    )
    if stock_status == "warning":
        condition.append(warning)
    elif stock_status == "normal":
        condition.append(~warning)
        condition.append(
            select(ProductSku.id)
            .where(ProductSku.product_id == Product.id, ProductSku.status == "active")
            .exists()
        )
    elif stock_status == "no_sku":
        condition.append(
            ~select(ProductSku.id)
            .where(ProductSku.product_id == Product.id, ProductSku.status == "active")
            .exists()
        )
    elif stock_status:
        raise HTTPException(status_code=422, detail="库存状态不正确")
    if profile_incomplete:
        condition.append(
            or_(
                Product.platform_item_code == "",
                Product.target_audience == "",
                Product.selling_points == "",
                Product.cost.is_(None),
            )
        )
    if sort not in {"newest", "updated"}:
        raise HTTPException(status_code=422, detail="排序方式不正确")
    base = select(Product).join(Store, Product.store_id == Store.id).where(*condition)
    total = db.scalar(select(func.count()).select_from(Product).join(Store).where(*condition)) or 0
    items = list(
        db.scalars(
            base.order_by(
                (Product.updated_at if sort == "updated" else Product.id).desc(), Product.id.desc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    # 分页后仅汇总当前页 SKU，避免逐商品查询与重复计数。
    sku_rows = (
        db.execute(
            select(
                ProductSku.product_id,
                func.count(ProductSku.id),
                func.min(ProductSku.price),
                func.max(ProductSku.price),
                func.max(case((ProductSku.stock < ProductSku.warning_threshold, 1), else_=0)),
            )
            .where(
                ProductSku.product_id.in_([item.id for item in items]),
                ProductSku.status == "active",
            )
            .group_by(ProductSku.product_id)
        ).all()
        if items
        else []
    )
    sku_by_product = {row[0]: row for row in sku_rows}
    return ProductList(
        items=[
            ProductListItem(
                **ProductRead.model_validate(item).model_dump(),
                sku_count=sku_by_product[item.id][1] if item.id in sku_by_product else 0,
                price_min=sku_by_product[item.id][2] if item.id in sku_by_product else None,
                price_max=sku_by_product[item.id][3] if item.id in sku_by_product else None,
                has_stock_warning=bool(sku_by_product[item.id][4])
                if item.id in sku_by_product
                else False,
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: SessionDep, access: Access) -> Product:
    store = _store(db, access, payload.store_id)
    if store.status != "active":
        raise HTTPException(status_code=409, detail="已归档店铺不能新建商品")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="商品名称不能为空")
    product = Product(
        store_id=store.id,
        name=name,
        category=payload.category.strip(),
        description=payload.description.strip(),
        platform_item_code=payload.platform_item_code.strip(),
        cost=payload.cost,
        target_audience=payload.target_audience.strip(),
        selling_points=payload.selling_points.strip(),
    )
    db.add(product)
    _commit(db)
    db.refresh(product)
    return product


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: SessionDep, access: Access) -> Product:
    return _product(db, access, product_id)


@router.patch("/products/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int, payload: ProductUpdate, db: SessionDep, access: Access
) -> Product:
    product = _product(db, access, product_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if (value is None and field != "cost") or (field == "name" and not value.strip()):
            raise HTTPException(status_code=422, detail="商品字段不能为空")
        setattr(product, field, value.strip() if isinstance(value, str) else value)
    _commit(db)
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
def archive_product(product_id: int, db: SessionDep, access: Access) -> None:
    _product(db, access, product_id).status = "archived"
    _commit(db)


@router.get("/products/{product_id}/skus", response_model=list[SkuRead])
def list_skus(product_id: int, db: SessionDep, access: Access) -> list[ProductSku]:
    _product(db, access, product_id)
    return list(
        db.scalars(
            select(ProductSku)
            .where(ProductSku.product_id == product_id, ProductSku.status == "active")
            .order_by(ProductSku.id)
        )
    )


@router.post(
    "/products/{product_id}/skus", response_model=SkuRead, status_code=status.HTTP_201_CREATED
)
def create_sku(product_id: int, payload: SkuCreate, db: SessionDep, access: Access) -> ProductSku:
    if _product(db, access, product_id).status != "active":
        raise HTTPException(status_code=409, detail="已归档商品不能新增 SKU")
    code, specification = payload.sku_code.strip(), payload.specification.strip()
    if not code or not specification:
        raise HTTPException(status_code=422, detail="SKU 编号和规格不能为空")
    sku = ProductSku(
        product_id=product_id,
        sku_code=code,
        specification=specification,
        price=payload.price,
        stock=payload.stock,
        warning_threshold=payload.warning_threshold,
    )
    db.add(sku)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU 编号在当前商品中已存在") from exc
    if payload.stock:
        db.add(
            InventoryMovement(
                product_id=product_id,
                sku_id=sku.id,
                actor_user_id=access.user.id,
                delta=payload.stock,
                quantity_after=payload.stock,
                reason="初始库存",
            )
        )
    _commit(db)
    db.refresh(sku)
    return sku


@router.patch("/products/{product_id}/skus/{sku_id}", response_model=SkuRead)
def update_sku(
    product_id: int, sku_id: int, payload: SkuUpdate, db: SessionDep, access: Access
) -> ProductSku:
    _product(db, access, product_id)
    sku = _sku(db, product_id, sku_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None or (field == "specification" and not value.strip()):
            raise HTTPException(status_code=422, detail="SKU 字段不能为空")
        setattr(sku, field, value.strip() if isinstance(value, str) else value)
    _commit(db)
    db.refresh(sku)
    return sku


@router.delete("/products/{product_id}/skus/{sku_id}", status_code=204)
def archive_sku(product_id: int, sku_id: int, db: SessionDep, access: Access) -> None:
    _product(db, access, product_id)
    _sku(db, product_id, sku_id).status = "archived"
    _commit(db)


@router.post(
    "/products/{product_id}/skus/{sku_id}/inventory",
    response_model=InventoryMovementRead,
    status_code=status.HTTP_201_CREATED,
)
def adjust_inventory(
    product_id: int, sku_id: int, payload: InventoryAdjust, db: SessionDep, access: Access
) -> InventoryMovement:
    _product(db, access, product_id)
    sku = _sku(db, product_id, sku_id, lock=True)
    if sku.status != "active":
        raise HTTPException(status_code=409, detail="已归档 SKU 不能调整库存")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="库存调整原因不能为空")
    if payload.quantity == sku.stock:
        raise HTTPException(status_code=409, detail="库存数量没有变化")
    movement = InventoryMovement(
        product_id=product_id,
        sku_id=sku.id,
        actor_user_id=access.user.id,
        delta=payload.quantity - sku.stock,
        quantity_after=payload.quantity,
        reason=reason,
    )
    sku.stock = payload.quantity
    db.add(movement)
    record_audit_event(
        db,
        access=access,
        action="inventory.adjusted",
        resource_type="sku",
        resource_id=str(sku.id),
        details={"quantity_after": payload.quantity, "delta": movement.delta},
    )
    _commit(db)
    db.refresh(movement)
    return movement


@router.get(
    "/products/{product_id}/inventory-movements", response_model=list[InventoryMovementRead]
)
def list_inventory_movements(
    product_id: int,
    db: SessionDep,
    access: Access,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[InventoryMovement]:
    _product(db, access, product_id)
    return list(
        db.scalars(
            select(InventoryMovement)
            .where(InventoryMovement.product_id == product_id)
            .order_by(InventoryMovement.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )


@router.get("/products/{product_id}/competitors", response_model=list[CompetitorRead])
def list_competitors(product_id: int, db: SessionDep, access: Access) -> list[Competitor]:
    _product(db, access, product_id)
    return list(
        db.scalars(
            select(Competitor)
            .where(Competitor.product_id == product_id)
            .order_by(Competitor.id.desc())
        )
    )


@router.post("/products/{product_id}/competitors/parse", response_model=CompetitorParseRead)
def parse_competitor_link(
    product_id: int, payload: CompetitorParse, db: SessionDep, access: Access
):
    """解析受支持公开链接中的显式参数；不抓取登录页，失败时保留原链接供人工补录。"""
    _product(db, access, product_id)
    parsed = urlparse(payload.source_url.strip())
    supported_hosts = {
        "item.taobao.com",
        "detail.tmall.com",
        "item.jd.com",
        "haohuo.jinritemai.com",
    }
    supported = parsed.scheme in {"http", "https"} and parsed.hostname in supported_hosts
    query = parse_qs(parsed.query)
    fields = {
        "name": query.get("name", [None])[0],
        "price": query.get("price", [None])[0],
        "category": query.get("category", [None])[0],
    }
    complete = supported and bool(fields["name"] and fields["price"])
    return CompetitorParseRead(
        source_url=payload.source_url,
        supported=supported,
        status="parsed" if complete else "manual_required",
        message="已读取链接中的公开参数" if complete else "链接可保留，请补录名称和价格",
        fields=fields,
        fetched_at=datetime.now(UTC) if complete else None,
    )


@router.post(
    "/products/{product_id}/competitors",
    response_model=CompetitorRead,
    status_code=status.HTTP_201_CREATED,
)
def create_competitor(
    product_id: int, payload: CompetitorCreate, db: SessionDep, access: Access
) -> Competitor:
    if _product(db, access, product_id).status != "active":
        raise HTTPException(status_code=409, detail="已归档商品不能新增竞品")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="竞品名称不能为空")
    source_status = "manual"
    source_fetched_at = None
    source_snapshot: dict = {}
    if payload.source_url:
        parsed = urlparse(payload.source_url.strip())
        supported_hosts = {
            "item.taobao.com",
            "detail.tmall.com",
            "item.jd.com",
            "haohuo.jinritemai.com",
        }
        query = parse_qs(parsed.query)
        complete = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname in supported_hosts
            and bool(query.get("name", [None])[0] and query.get("price", [None])[0])
        )
        source_status = "parsed" if complete else "manual_required"
        source_fetched_at = datetime.now(UTC) if complete else None
        source_snapshot = {
            "name": query.get("name", [None])[0],
            "price": query.get("price", [None])[0],
            "category": query.get("category", [None])[0],
        }
    competitor = Competitor(
        product_id=product_id,
        name=name,
        price=payload.price,
        attributes=payload.attributes,
        source_url=payload.source_url,
        source_status=source_status,
        source_fetched_at=source_fetched_at,
        source_snapshot=source_snapshot,
    )
    db.add(competitor)
    _commit(db)
    db.refresh(competitor)
    return competitor


@router.patch("/products/{product_id}/competitors/{competitor_id}", response_model=CompetitorRead)
def update_competitor(
    product_id: int, competitor_id: int, payload: CompetitorUpdate, db: SessionDep, access: Access
) -> Competitor:
    _product(db, access, product_id)
    competitor = db.scalar(
        select(Competitor).where(
            Competitor.id == competitor_id, Competitor.product_id == product_id
        )
    )
    if competitor is None:
        raise HTTPException(status_code=404, detail="竞品不属于当前商品")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None and field != "source_url":
            raise HTTPException(status_code=422, detail="竞品字段不能为空")
        if field == "name" and not value.strip():
            raise HTTPException(status_code=422, detail="竞品名称不能为空")
        setattr(competitor, field, value.strip() if isinstance(value, str) else value)
    _commit(db)
    db.refresh(competitor)
    return competitor


@router.delete("/products/{product_id}/competitors/{competitor_id}", status_code=204)
def delete_competitor(product_id: int, competitor_id: int, db: SessionDep, access: Access) -> None:
    _product(db, access, product_id)
    competitor = db.scalar(
        select(Competitor).where(
            Competitor.id == competitor_id, Competitor.product_id == product_id
        )
    )
    if competitor is None:
        raise HTTPException(status_code=404, detail="竞品不属于当前商品")
    db.delete(competitor)
    _commit(db)


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(db: SessionDep, access: Access) -> DashboardSummary:
    workspace_id = access.workspace.id
    store_count = (
        db.scalar(
            select(func.count())
            .select_from(Store)
            .where(Store.workspace_id == workspace_id, Store.status == "active")
        )
        or 0
    )
    product_count = (
        db.scalar(
            select(func.count())
            .select_from(Product)
            .join(Store)
            .where(
                Store.workspace_id == workspace_id,
                Store.status == "active",
                Product.status == "active",
            )
        )
        or 0
    )
    warning_rows = db.execute(
        select(ProductSku, Product, Store)
        .join(Product, ProductSku.product_id == Product.id)
        .join(Store, Product.store_id == Store.id)
        .where(
            Store.workspace_id == workspace_id,
            Store.status == "active",
            Product.status == "active",
            ProductSku.status == "active",
            ProductSku.stock < ProductSku.warning_threshold,
        )
        .order_by(ProductSku.stock.asc(), ProductSku.id.asc())
    ).all()
    warnings = [
        StockWarning(
            store_id=store.id,
            product_id=product.id,
            product_name=product.name,
            sku_id=sku.id,
            sku_code=sku.sku_code,
            stock=sku.stock,
            warning_threshold=sku.warning_threshold,
        )
        for sku, product, store in warning_rows
    ]
    return DashboardSummary(
        store_count=store_count,
        product_count=product_count,
        warning_count=len(warnings),
        warnings=warnings[:20],
    )


@router.get("/trends", response_model=TrendsRead)
def trends(
    db: SessionDep,
    access: Access,
    store_id: int | None = None,
    product_id: int | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> TrendsRead:
    """按当前工作区返回实际存在的经营周期；缺失周期不填充为零。"""
    conditions = [
        Store.workspace_id == access.workspace.id,
        Store.status == "active",
        Product.status == "active",
    ]
    if store_id is not None:
        _store(db, access, store_id)
        conditions.append(Store.id == store_id)
    if product_id is not None:
        _product(db, access, product_id)
        conditions.append(Product.id == product_id)
    if period_start is not None:
        conditions.append(BusinessMetric.period_end >= period_start)
    if period_end is not None:
        conditions.append(BusinessMetric.period_start <= period_end)
    stores = list(
        db.scalars(
            select(Store).where(
                Store.workspace_id == access.workspace.id,
                Store.status == "active",
                *([Store.id == store_id] if store_id else []),
            )
        )
    )
    rows = db.execute(
        select(BusinessMetric, Product, Store)
        .join(Product, BusinessMetric.product_id == Product.id)
        .join(Store, Product.store_id == Store.id)
        .where(*conditions)
        .order_by(Product.id, BusinessMetric.period_start)
    ).all()
    grouped: dict[int, ProductTrendRead] = {}
    for metric, product, store in rows:
        series = grouped.setdefault(
            product.id,
            ProductTrendRead(
                product_id=product.id,
                product_name=product.name,
                store_id=store.id,
                store_name=store.name,
                points=[],
            ),
        )
        series.points.append(
            TrendPoint(
                period_start=metric.period_start,
                period_end=metric.period_end,
                actual_gmv=metric.actual_gmv,
                target_gmv=metric.target_gmv,
                actual_roi=metric.actual_roi,
                actual_conversion_rate=metric.actual_conversion_rate,
            )
        )
    return TrendsRead(
        period_start=period_start,
        period_end=period_end,
        stores=[
            StoreRead.model_validate(store).model_copy(update={"product_count": 0})
            for store in stores
        ],
        series=list(grouped.values()),
    )


@router.post("/demo/wireless-charger", response_model=DemoSeedRead, status_code=201)
def seed_wireless_charger_demo(
    db: SessionDep,
    access: Annotated[
        WorkspaceAccess, Depends(require_roles(WorkspaceRole.SUPERVISOR, WorkspaceRole.ADMIN))
    ],
):
    """幂等补齐全流程演示数据；所有记录都带有模拟标记，不代表真实经营数据。"""
    demo_key = "demo-wireless-charger-v1"
    now = datetime.now(UTC)
    store = db.scalar(
        select(Store).where(Store.workspace_id == access.workspace.id, Store.name == "无线充演示店")
    )
    created = store is None
    store = store or Store(workspace_id=access.workspace.id, name="无线充演示店", platform="淘宝")
    if store.id is None:
        db.add(store)
        db.flush()
    product = db.scalar(
        select(Product).where(
            Product.store_id == store.id, Product.name == "无线充热销款（模拟演示）"
        )
    )
    if product is None:
        product = Product(
            store_id=store.id,
            name="无线充热销款（模拟演示）",
            category="3C 数码",
            description="[模拟演示数据] 低价竞品冲击下的无线充热销款防守场景",
            target_audience="[模拟演示数据] 通勤办公人群",
            selling_points="[模拟演示数据] 15W 快充、折叠便携",
        )
        db.add(product)
        db.flush()
        created = True

    # 多规格库存包含正常和预警状态，便于查看大盘与库存流水。
    sku_specs = [
        ("WLC-15W", "黑色 15W（模拟）", Decimal("129.00"), 88, 20),
        ("WLC-15W-WHITE", "白色 15W（模拟）", Decimal("139.00"), 6, 12),
        ("WLC-FOLD", "折叠款 15W（模拟）", Decimal("159.00"), 42, 10),
    ]
    skus: list[ProductSku] = []
    for sku_code, specification, price, stock, threshold in sku_specs:
        sku = db.scalar(
            select(ProductSku).where(
                ProductSku.product_id == product.id, ProductSku.sku_code == sku_code
            )
        )
        if sku is None:
            sku = ProductSku(
                product_id=product.id,
                sku_code=sku_code,
                specification=specification,
                price=price,
                stock=stock,
                warning_threshold=threshold,
            )
            db.add(sku)
            db.flush()
        skus.append(sku)
        movement_reason = f"[模拟演示数据] {demo_key} 期初库存"
        if db.scalar(
            select(InventoryMovement.id).where(
                InventoryMovement.sku_id == sku.id,
                InventoryMovement.reason == movement_reason,
            )
        ) is None:
            db.add(
                InventoryMovement(
                    product_id=product.id,
                    sku_id=sku.id,
                    actor_user_id=access.user.id,
                    delta=stock,
                    quantity_after=stock,
                    reason=movement_reason,
                )
            )

    competitor_specs = [
        ("低价无线充竞品（模拟）", Decimal("79.00"), {"功率": "15W", "场景": "低价冲击"}),
        ("磁吸无线充竞品（模拟）", Decimal("119.00"), {"功率": "15W", "接口": "磁吸"}),
        ("桌面折叠充电座（模拟）", Decimal("169.00"), {"功率": "20W", "材质": "铝合金"}),
    ]
    for name, price, attributes in competitor_specs:
        if db.scalar(
            select(Competitor.id).where(
                Competitor.product_id == product.id, Competitor.name == name
            )
        ) is None:
            db.add(
                Competitor(
                    product_id=product.id,
                    name=name,
                    price=price,
                    attributes=attributes,
                    source_status="manual",
                    source_snapshot={"demo_key": demo_key},
                )
            )

    # 创意、媒体库和复盘页面共用同一商品下的可确认版本。
    content_templates = {
        "diagnosis": [
            {"finding": "低价竞品集中在 79 元区间", "recommendation": "突出折叠便携和质保差异"},
            {"finding": "白色规格库存偏低", "recommendation": "活动前优先补充白色款库存"},
            {"finding": "桌面场景转化较高", "recommendation": "扩展办公桌和差旅场景素材"},
        ],
        "image_idea": [
            {"idea": "办公桌面折叠无线充对比创意", "headline": "桌面更整洁，充电更省心"},
            {"idea": "15W 快充功率与兼容设备展示", "headline": "通勤办公，快速补能"},
            {"idea": "折叠收纳和差旅便携场景", "headline": "收起即走，轻松出差"},
        ],
        "video_script": [
            {"script": "展示通勤收纳与 15W 快充场景", "hook": "包里少一根线"},
            {"script": "办公桌前单手展开并开始充电", "hook": "桌面充电一步到位"},
            {"script": "对比普通支架与折叠磁吸底座", "hook": "稳固与便携可以兼得"},
        ],
    }
    versions: dict[str, list[ContentVersion]] = {}
    for content_type, examples in content_templates.items():
        versions[content_type] = []
        for version_no, example in enumerate(examples, start=1):
            version = db.scalar(
                select(ContentVersion).where(
                    ContentVersion.product_id == product.id,
                    ContentVersion.content_type == content_type,
                    ContentVersion.slot_key == "demo-wireless",
                    ContentVersion.version_no == version_no,
                )
            )
            if version is None:
                version = ContentVersion(
                    product_id=product.id,
                    content_type=content_type,
                    slot_key="demo-wireless",
                    version_no=version_no,
                    status="confirmed",
                    source="human",
                    content={"label": "模拟演示数据", **example},
                    updated_by=access.user.id,
                )
                db.add(version)
                db.flush()
            versions[content_type].append(version)

    # 四个连续经营周期用于趋势图和周期对比。
    metrics: list[BusinessMetric] = []
    metric_values = [
        (date(2026, 1, 1), date(2026, 1, 31), 18000, 15600, 2.1),
        (date(2026, 2, 1), date(2026, 2, 28), 19000, 18400, 2.4),
        (date(2026, 3, 1), date(2026, 3, 31), 21000, 22800, 2.8),
        (date(2026, 4, 1), date(2026, 4, 30), 23000, 21600, 2.6),
    ]
    for period_start, period_end, target_gmv, actual_gmv, roi in metric_values:
        metric = db.scalar(
            select(BusinessMetric).where(
                BusinessMetric.product_id == product.id,
                BusinessMetric.period_start == period_start,
                BusinessMetric.period_end == period_end,
                BusinessMetric.source == "demo",
            )
        )
        if metric is None:
            metric = BusinessMetric(
                workspace_id=access.workspace.id,
                product_id=product.id,
                period_start=period_start,
                period_end=period_end,
                source="demo",
                target_gmv=Decimal(target_gmv),
                actual_gmv=Decimal(actual_gmv),
                target_impressions=10000,
                actual_impressions=11200,
                target_ctr=Decimal("0.08"),
                actual_ctr=Decimal("0.075"),
                target_conversion_rate=Decimal("0.04"),
                actual_conversion_rate=Decimal("0.035"),
                target_roi=Decimal("2.5"),
                actual_roi=Decimal(str(roi)),
                created_by=access.user.id,
            )
            db.add(metric)
            db.flush()
        metrics.append(metric)

    # 媒体列表提供通过、待审核、驳回及失败状态，文件路径标记为虚拟演示素材。
    media_examples = [
        ("image", 1, "approved", "succeeded"),
        ("image", 2, "pending", "succeeded"),
        ("video", 1, "rejected", "succeeded"),
        ("video", 2, "pending", "failed"),
    ]
    for media_type, version_no, review_status, job_status in media_examples:
        content_type = "image_idea" if media_type == "image" else "video_script"
        content_version = versions[content_type][version_no - 1]
        idempotency_key = f"{demo_key}-{media_type}-v{version_no}"
        job = db.scalar(
            select(GenerationJob).where(
                GenerationJob.workspace_id == access.workspace.id,
                GenerationJob.idempotency_key == idempotency_key,
            )
        )
        if job is None:
            job = GenerationJob(
                workspace_id=access.workspace.id,
                product_id=product.id,
                content_version_id=content_version.id,
                media_type=media_type,
                idempotency_key=idempotency_key,
                status=job_status,
                provider="demo",
                attempts=1,
                max_retries=3,
                error_code="demo_provider_unavailable" if job_status == "failed" else None,
                error_message=(
                    "[模拟演示数据] 示例任务失败，可体验重试操作"
                    if job_status == "failed"
                    else None
                ),
                created_by=access.user.id,
                started_at=now,
                finished_at=now,
            )
            db.add(job)
            db.flush()
            db.add(
                GenerationEvent(
                    job_id=job.id,
                    status=job_status,
                    message=(
                        "[模拟演示数据] 示例任务已完成"
                        if job_status == "succeeded"
                        else "[模拟演示数据] 示例任务失败，可重试"
                    ),
                    details={"demo_key": demo_key},
                )
            )
        if job_status == "succeeded" and db.scalar(
            select(MediaAsset.id).where(MediaAsset.job_id == job.id)
        ) is None:
            db.add(
                MediaAsset(
                    workspace_id=access.workspace.id,
                    product_id=product.id,
                    job_id=job.id,
                    content_version_id=content_version.id,
                    media_type=media_type,
                    storage_path=f"demo/{demo_key}/{media_type}-v{version_no}.txt",
                    status="available",
                    review_status=review_status,
                    tags=["模拟演示数据", "主图" if media_type == "image" else "短视频"],
                    updated_by=access.user.id,
                )
            )

    # 用待审批任务演示 Agent checkpoint 与人工审批入口。
    agent_name = "无线充商品经营分析（模拟待审批）"
    task = db.scalar(
        select(AgentTask).where(
            AgentTask.workspace_id == access.workspace.id,
            AgentTask.product_id == product.id,
            AgentTask.name == agent_name,
        )
    )
    if task is None:
        task = AgentTask(
            workspace_id=access.workspace.id,
            product_id=product.id,
            created_by=access.user.id,
            name=agent_name,
            goal="[模拟演示数据] 汇总经营表现并提交建议供主管审核",
            requested_tools=[
                "catalog_snapshot",
                "content_summary",
                "performance_summary",
                "recommendation_draft",
                "recommendation_publish",
            ],
            context={"product_name": product.name, "demo_key": demo_key},
            status="waiting_approval",
            current_step=5,
            checkpoint_version=4,
            paused_at=now,
        )
        db.add(task)
        db.flush()
        step_examples = [
            (
                "catalog_snapshot",
                "succeeded",
                {"sku_count": len(skus), "stock_total": sum(sku.stock for sku in skus)},
            ),
            ("content_summary", "succeeded", {"confirmed_count": 9}),
            (
                "performance_summary",
                "succeeded",
                {"period_count": len(metrics), "actual_gmv": "78400.00"},
            ),
            ("recommendation_draft", "succeeded", {"recommendation": "提升折叠便携卖点曝光"}),
            ("approval_gate", "waiting_approval", {}),
            ("recommendation_publish", "pending", {}),
        ]
        steps = []
        for step_no, (tool_name, step_status, output) in enumerate(step_examples, start=1):
            step = AgentStep(
                task_id=task.id,
                step_no=step_no,
                tool_name=tool_name,
                status=step_status,
                input_summary={"demo_key": demo_key},
                output_summary={"label": "模拟演示数据", **output},
                checkpoint={"version": step_no} if step_status == "succeeded" else {},
                started_at=now,
                finished_at=now if step_status == "succeeded" else None,
            )
            db.add(step)
            steps.append(step)
        db.flush()
        db.add(
            AgentApproval(
                task_id=task.id,
                step_id=steps[4].id,
                workspace_id=access.workspace.id,
                risk_level="high",
                status="pending",
                requested_by=access.user.id,
            )
        )

    # 追加待审核的投放建议和每期复盘快照，便于从单品页体验审批链路。
    proposal_specs = [
        ("normal", "模拟常规素材实验：测试折叠便携卖点"),
        ("high", "模拟高风险预算调整：需要主管审批"),
    ]
    for risk_level, strategy in proposal_specs:
        demo_content = {"label": "模拟演示数据", "demo_key": demo_key, "strategy": strategy}
        if not any(
            proposal.content.get("demo_key") == demo_key
            and proposal.content.get("strategy") == strategy
            for proposal in db.scalars(
                select(AdProposal).where(AdProposal.product_id == product.id)
            )
        ):
            db.add(
                AdProposal(
                    workspace_id=access.workspace.id,
                    product_id=product.id,
                    content=demo_content,
                    risk_level=risk_level,
                    status="pending",
                    submitted_by=access.user.id,
                )
            )
    existing_reports = list(
        db.scalars(select(ReviewReport).where(ReviewReport.product_id == product.id))
    )
    for metric in metrics:
        if not any(
            report.metric_id == metric.id and report.content.get("demo_key") == demo_key
            for report in existing_reports
        ):
            report = ReviewReport(
                workspace_id=access.workspace.id,
                product_id=product.id,
                metric_id=metric.id,
                content={
                    "label": "模拟演示数据",
                    "demo_key": demo_key,
                    "summary": "根据竞品价格、库存和经营周期优化卖点与补货节奏",
                    "action_items": ["补充白色规格库存", "测试办公桌面创意"],
                },
                created_by=access.user.id,
                status="draft",
            )
            db.add(report)
            existing_reports.append(report)

    # 待确认批次展示导入预览中的有效行和错误行；确认后只会增加一件模拟商品。
    import_batch_key = f"{demo_key}-products-import"
    if db.scalar(
        select(ImportBatch.id).where(
            ImportBatch.workspace_id == access.workspace.id,
            ImportBatch.batch_key == import_batch_key,
        )
    ) is None:
        import_rows = [
            {
                "line": 2,
                "data": {
                    "store_id": str(store.id),
                    "name": "导入流程体验商品（模拟）",
                    "category": "3C 数码",
                    "description": "[模拟演示数据] 可在导入中心预览并确认导入",
                    "platform_item_code": "DEMO-IMPORT-WLC-01",
                    "cost": "58.00",
                    "target_audience": "通勤办公人群",
                    "selling_points": "导入确认流程演示",
                },
                "valid": True,
                "errors": [],
            },
            {
                "line": 3,
                "data": {
                    "store_id": "-1",
                    "name": "",
                    "category": "3C 数码",
                    "description": "[模拟演示数据] 错误行不会被导入",
                    "platform_item_code": "DEMO-IMPORT-INVALID",
                    "cost": "-1",
                    "target_audience": "",
                    "selling_points": "",
                },
                "valid": False,
                "errors": [
                    "store_id 不属于当前工作空间",
                    "name 不能为空",
                    "cost 不能为负数",
                ],
            },
        ]
        db.add(
            ImportBatch(
                workspace_id=access.workspace.id,
                batch_key=import_batch_key,
                data_type="products",
                filename="wireless-charger-demo.csv",
                status="preview",
                version=1,
                rows=import_rows,
                valid_count=1,
                error_count=1,
                created_by=access.user.id,
            )
        )

    # 第二个店铺和商品用于演示跨店铺经营趋势与商品筛选。
    second_store = db.scalar(
        select(Store).where(
            Store.workspace_id == access.workspace.id, Store.name == "无线充京东演示店"
        )
    )
    if second_store is None:
        second_store = Store(
            workspace_id=access.workspace.id,
            name="无线充京东演示店",
            platform="京东",
        )
        db.add(second_store)
        db.flush()
        created = True
    second_product = db.scalar(
        select(Product).where(
            Product.store_id == second_store.id, Product.name == "双线圈无线充电座（模拟演示）"
        )
    )
    if second_product is None:
        second_product = Product(
            store_id=second_store.id,
            name="双线圈无线充电座（模拟演示）",
            category="3C 数码",
            description="[模拟演示数据] 京东店铺的多设备无线充场景",
            target_audience="[模拟演示数据] 家庭与办公多设备用户",
            selling_points="[模拟演示数据] 双线圈、横竖可充",
        )
        db.add(second_product)
        db.flush()
        created = True
    second_sku = db.scalar(
        select(ProductSku).where(
            ProductSku.product_id == second_product.id, ProductSku.sku_code == "WLC-DUAL-01"
        )
    )
    if second_sku is None:
        second_sku = ProductSku(
            product_id=second_product.id,
            sku_code="WLC-DUAL-01",
            specification="双线圈 黑色（模拟）",
            price=Decimal("189.00"),
            stock=31,
            warning_threshold=10,
        )
        db.add(second_sku)
        db.flush()
    if db.scalar(
        select(Competitor.id).where(
            Competitor.product_id == second_product.id,
            Competitor.name == "双线圈磁吸竞品（模拟）",
        )
    ) is None:
        db.add(
            Competitor(
                product_id=second_product.id,
                name="双线圈磁吸竞品（模拟）",
                price=Decimal("199.00"),
                attributes={"线圈": "双线圈", "认证": "Qi2"},
                source_status="manual",
                source_snapshot={"demo_key": demo_key},
            )
        )
    for period_start, period_end, target_gmv, actual_gmv, roi in metric_values[1:]:
        if db.scalar(
            select(BusinessMetric.id).where(
                BusinessMetric.product_id == second_product.id,
                BusinessMetric.period_start == period_start,
                BusinessMetric.period_end == period_end,
                BusinessMetric.source == "demo",
            )
        ) is None:
            db.add(
                BusinessMetric(
                    workspace_id=access.workspace.id,
                    product_id=second_product.id,
                    period_start=period_start,
                    period_end=period_end,
                    source="demo",
                    target_gmv=Decimal(target_gmv),
                    actual_gmv=Decimal(actual_gmv) * Decimal("1.04"),
                    target_impressions=7200,
                    actual_impressions=7900,
                    target_ctr=Decimal("0.07"),
                    actual_ctr=Decimal("0.076"),
                    target_conversion_rate=Decimal("0.035"),
                    actual_conversion_rate=Decimal("0.038"),
                    target_roi=Decimal("2.3"),
                    actual_roi=Decimal(str(roi)),
                    created_by=access.user.id,
                )
            )

    record_audit_event(
        db,
        access=access,
        action="catalog.demo_seed",
        resource_type="product",
        resource_id=str(product.id),
        details={"demo_key": demo_key, "created": created},
    )
    db.commit()
    included = [
        "2 个演示店铺、2 件演示商品和多规格库存",
        "竞品对标、结构化诊断与多版本创意",
        "4 个连续经营周期、趋势对比与复盘报告",
        "通过/待审核/驳回/失败素材及任务时间线",
        "待审批的 Agent 任务与普通/高风险投放建议",
        "导入中心的一条有效预览行和一条错误行，可自行确认有效数据",
        "所有演示记录均标注为模拟数据，可重复补齐",
    ]
    return DemoSeedRead(
        demo_key=demo_key,
        product_id=product.id,
        store_id=store.id,
        created=created,
        label="模拟/演示数据",
        included=included,
    )
