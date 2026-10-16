"""M3 配置接口契约；输入模型禁止携带密钥或平台凭据。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Target = Literal["text", "image", "video"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceConfigUpdate(StrictInput):
    provider: Literal["openai", "jimeng", "dashscope", "none"]
    model: str = Field(default="", max_length=120, pattern=r"^[A-Za-z0-9._:-]*$")


class ServiceConfigRead(BaseModel):
    target: Target
    provider: str
    model: str
    has_api_key: bool
    configured: bool
    key_source: Literal["environment"] = "environment"


class TaskRulesUpdate(StrictInput):
    timeout_seconds: int = Field(ge=30, le=3600)
    max_retries: int = Field(ge=0, le=10)
    max_concurrency: int = Field(ge=1, le=32)
    image_poll_interval_seconds: int = Field(ge=2, le=120)
    image_poll_max_attempts: int = Field(ge=1, le=100)
    video_poll_interval_seconds: int = Field(ge=2, le=120)
    video_poll_max_attempts: int = Field(ge=1, le=100)


class PlatformAccountUpdate(StrictInput):
    account_identifier: str = Field(default="", max_length=120)
    authorization_status: Literal["not_connected", "placeholder"]


class PlatformAccountRead(BaseModel):
    store_id: int
    store_name: str
    platform: str
    account_identifier: str
    authorization_status: str


class SettingsRead(BaseModel):
    services: list[ServiceConfigRead]
    rules: TaskRulesUpdate
    platforms: list[PlatformAccountRead]


class ConnectionCheckRead(BaseModel):
    target: Target
    ok: bool
    code: str
    message: str
    checked_at: datetime


class ConfigAuditRead(BaseModel):
    id: int
    actor_name: str
    action: str
    resource_type: str
    resource_id: str | None
    details: dict | None
    created_at: datetime
