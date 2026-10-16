"""M5 媒体任务与素材审核的输入输出模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MediaType = Literal["image", "video"]
JobStatus = Literal["pending", "running", "succeeded", "failed", "timeout", "cancelled"]


class JobCreate(BaseModel):
    media_type: MediaType
    content_version_id: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=120)


class AssetUpdate(BaseModel):
    review_status: Literal["pending", "approved", "rejected"] | None = None
    tags: list[str] | None = Field(default=None, max_length=20)


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    message: str
    details: dict | None
    created_at: datetime


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    job_id: int
    content_version_id: int
    media_type: MediaType
    storage_path: str
    status: str
    review_status: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    content_version_id: int
    media_type: MediaType
    idempotency_key: str
    status: JobStatus
    provider: str
    attempts: int
    max_retries: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    events: list[EventRead] = Field(default_factory=list)
    asset: AssetRead | None = None
