"""M7 经营指标与复盘报告契约。"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MetricCreate(BaseModel):
    period_start: date
    period_end: date
    source: str = Field(default="manual", min_length=1, max_length=40)
    target_gmv: Decimal = Field(ge=0)
    actual_gmv: Decimal = Field(ge=0)
    target_impressions: int = Field(ge=0)
    actual_impressions: int = Field(ge=0)
    target_ctr: Decimal = Field(ge=0, le=1)
    actual_ctr: Decimal = Field(ge=0, le=1)
    target_conversion_rate: Decimal = Field(ge=0, le=1)
    actual_conversion_rate: Decimal = Field(ge=0, le=1)
    target_roi: Decimal = Field(ge=0)
    actual_roi: Decimal = Field(ge=0)


class MetricRead(MetricCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    created_by: int
    created_at: datetime
    updated_at: datetime


class ReportUpdate(BaseModel):
    revision: int = Field(ge=1)
    content: dict = Field(min_length=1)


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    metric_id: int
    content: dict
    revision: int
    status: str
    created_by: int
    created_at: datetime
    updated_at: datetime
