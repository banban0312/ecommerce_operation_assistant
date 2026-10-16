"""M8 导入预览和确认响应。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ImportPreviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_key: str
    data_type: Literal["products", "skus", "metrics"]
    filename: str
    status: str
    version: int
    rows: list[dict]
    valid_count: int
    error_count: int
    created_at: datetime


class ImportCommit(BaseModel):
    version: int = Field(ge=1)
