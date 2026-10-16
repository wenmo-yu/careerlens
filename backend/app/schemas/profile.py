from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProfileItemRead(BaseModel):
    id: str
    user_id: str
    category: str
    name: str
    level: int
    confidence: float
    evidence_ids: list[str]
    details: dict[str, Any]
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProfileRead(BaseModel):
    user_id: str
    items: list[ProfileItemRead]
    count: int


class ProfileProposalCreate(BaseModel):
    message: str = Field(min_length=1, max_length=3000)


class ProfileProposalDecision(BaseModel):
    approve: bool


class ProfileProposalRead(BaseModel):
    id: str
    user_id: str
    message: str
    changes: list[dict[str, Any]]
    status: str
    created_at: datetime
    resolved_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
