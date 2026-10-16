"""店铺、商品、SKU、库存和竞品接口；所有资源都先校验工作空间归属。"""

from datetime import UTC, date, datetime
from typing import Annotated
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import SessionDep, get_workspace_access
from app.models import BusinessMetric, Competitor, InventoryMovement, Product, ProductSku, Store
from app.schemas.catalog import (
    CompetitorCreate,
    CompetitorParse,
    CompetitorParseRead,
    CompetitorRead,
    CompetitorUpdate,
    DashboardSummary,
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
