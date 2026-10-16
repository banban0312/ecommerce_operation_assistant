"""M10 Agent 任务、步骤和人工审批契约。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolRead(BaseModel):
    name: str
    label: str
    description: str
    protected: bool


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    goal: str = Field(default="", max_length=2000)
    requested_tools: list[str] = Field(default_factory=list, max_length=10)
    require_approval: bool = True


class ApprovalDecision(BaseModel):
    result: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=1000)


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    step_no: int
    tool_name: str
    status: str
    input_summary: dict
    output_summary: dict
    checkpoint: dict
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    step_id: int
    risk_level: str
    status: str
    requested_by: int
    decided_by: int | None
    decision_note: str
    created_at: datetime
    decided_at: datetime | None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    name: str
    goal: str
    requested_tools: list[str]
    context: dict
    status: str
    current_step: int
    checkpoint_version: int
    error_message: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime
    paused_at: datetime | None
    finished_at: datetime | None
    steps: list[StepRead] = Field(default_factory=list)
    approvals: list[ApprovalRead] = Field(default_factory=list)
