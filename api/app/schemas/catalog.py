"""商品主数据的输入约束和对外响应。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    platform: str = Field(min_length=1, max_length=50)


class StoreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    platform: str | None = Field(default=None, min_length=1, max_length=50)
    status: Literal["active", "archived"] | None = None


class StoreRead(ReadModel):
    id: int
    workspace_id: int
    name: str
    platform: str
    status: str
    created_at: datetime
    product_count: int = 0


class ProductCreate(BaseModel):
    store_id: int
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=5000)
    platform_item_code: str = Field(default="", max_length=100)
    cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    target_audience: str = Field(default="", max_length=500)
    selling_points: str = Field(default="", max_length=5000)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    platform_item_code: str | None = Field(default=None, max_length=100)
    cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    target_audience: str | None = Field(default=None, max_length=500)
    selling_points: str | None = Field(default=None, max_length=5000)
    status: Literal["active", "archived"] | None = None


class ProductRead(ReadModel):
    id: int
    store_id: int
    name: str
    category: str
    description: str
    platform_item_code: str
    cost: Decimal | None
    target_audience: str
    selling_points: str
    status: str
    created_at: datetime
    updated_at: datetime


class ProductListItem(ProductRead):
    sku_count: int = 0
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    has_stock_warning: bool = False


class ProductList(BaseModel):
    items: list[ProductListItem]
    total: int
    page: int
    page_size: int


class SkuCreate(BaseModel):
    sku_code: str = Field(min_length=1, max_length=100)
    specification: str = Field(min_length=1, max_length=200)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    stock: int = Field(default=0, ge=0)
    warning_threshold: int = Field(default=0, ge=0)


class SkuUpdate(BaseModel):
    specification: str | None = Field(default=None, min_length=1, max_length=200)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    warning_threshold: int | None = Field(default=None, ge=0)
    status: Literal["active", "archived"] | None = None


class SkuRead(ReadModel):
    id: int
    product_id: int
    sku_code: str
    specification: str
    price: Decimal
    stock: int
    warning_threshold: int
    status: str
    created_at: datetime


class InventoryAdjust(BaseModel):
    quantity: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=200)


class InventoryMovementRead(ReadModel):
    id: int
    product_id: int
    sku_id: int
    actor_user_id: int
    delta: int
    quantity_after: int
    reason: str
    created_at: datetime


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    attributes: dict[str, str] = Field(default_factory=dict)
    source_url: str | None = Field(default=None, max_length=1000)


class CompetitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    attributes: dict[str, str] | None = None
    source_url: str | None = Field(default=None, max_length=1000)


class CompetitorRead(ReadModel):
    id: int
    product_id: int
    name: str
    price: Decimal
    attributes: dict[str, str]
    source_url: str | None
    source_status: str
    source_fetched_at: datetime | None
    source_snapshot: dict
    created_at: datetime


class CompetitorParse(BaseModel):
    source_url: str = Field(min_length=1, max_length=1000)


class CompetitorParseRead(BaseModel):
    source_url: str
    supported: bool
    status: str
    message: str
    fields: dict[str, str | None]
    fetched_at: datetime | None = None


class TrendPoint(BaseModel):
    period_start: date
    period_end: date
    actual_gmv: Decimal | None = None
    target_gmv: Decimal | None = None
    actual_roi: Decimal | None = None
    actual_conversion_rate: Decimal | None = None


class ProductTrendRead(BaseModel):
    product_id: int
    product_name: str
    store_id: int
    store_name: str
    points: list[TrendPoint]


class TrendsRead(BaseModel):
    period_start: date | None
    period_end: date | None
    stores: list[StoreRead]
    series: list[ProductTrendRead]


class StockWarning(BaseModel):
    store_id: int
    product_id: int
    product_name: str
    sku_id: int
    sku_code: str
    stock: int
    warning_threshold: int


class DashboardSummary(BaseModel):
    store_count: int
    product_count: int
    warning_count: int
    warnings: list[StockWarning]
