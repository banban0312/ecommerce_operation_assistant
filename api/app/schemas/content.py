"""M4 结构化诊断、创意和脚本的接口契约。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ContentType = Literal["diagnosis", "image_idea", "video_script"]
ContentStatus = Literal["draft", "confirmed", "archived"]


class ContentUpdate(BaseModel):
    """编辑时必须携带读取到的 revision，防止旧页面覆盖新修改。"""

    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    content: dict = Field(min_length=1)


class ContentRead(BaseModel):
    id: int
    product_id: int
    content_type: ContentType
    slot_key: str
    version_no: int
    revision: int
    status: ContentStatus
    source: Literal["model", "human"]
    content: dict
    updated_by: int
    created_at: datetime
    updated_at: datetime


class ContentBundle(BaseModel):
    product_id: int
    diagnosis: list[ContentRead]
    image_ideas: list[ContentRead]
    video_scripts: list[ContentRead]


class GenerationRead(BaseModel):
    message: str
    items: list[ContentRead]
