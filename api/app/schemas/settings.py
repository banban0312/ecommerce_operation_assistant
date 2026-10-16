"""M3 配置接口契约；服务密钥仅允许管理员配置且不会出现在读取响应。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Target = Literal["text", "image", "video"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceConfigUpdate(StrictInput):
    provider: Literal["openai", "jimeng", "dashscope", "none"]
    model: str = Field(default="", max_length=120, pattern=r"^[A-Za-z0-9._:/-]*$")
    endpoint_url: str = Field(default="", max_length=1000)
    api_key: str | None = Field(default=None, max_length=4096)
    clear_api_key: bool = False

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            return value
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            raise ValueError("服务地址必须是有效的 HTTP/HTTPS URL，且不能包含账号密码")
        if parsed.query or parsed.fragment:
            raise ValueError("服务地址不能包含查询参数或片段")
        return value

    @field_validator("api_key")
    @classmethod
    def trim_api_key(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class ServiceConfigRead(BaseModel):
    target: Target
    provider: str
    model: str
    endpoint_url: str
    has_api_key: bool
    configured: bool
    key_source: Literal["environment", "workspace"]


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
