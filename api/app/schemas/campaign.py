"""M6 投放建议与人工决策契约。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProposalUpdate(BaseModel):
    revision: int = Field(ge=1)
    content: dict = Field(min_length=1)


class ProposalCreate(BaseModel):
    risk_level: Literal["normal", "high"] = "normal"


class RiskUpdate(BaseModel):
    risk_level: Literal["normal", "high"]
    revision: int = Field(ge=1)


class DecisionCreate(BaseModel):
    revision: int = Field(ge=1)
    result: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=1000)


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    proposal_id: int
    actor_user_id: int
    actor_role: str
    result: str
    note: str
    previous_risk_level: str
    risk_level: str
    created_at: datetime


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    content: dict
    risk_level: str
    status: str
    revision: int
    submitted_by: int
    created_at: datetime
    updated_at: datetime
    decisions: list[DecisionRead] = Field(default_factory=list)
