from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    title: str = Field(default="", max_length=200)
    workspace_id: str = Field(default="default", max_length=36)


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    workspace_id: str
    title: str
    head_revision: int
    runtime_generation: int
    status: str
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    run_id: str | None
    role: Literal["user", "assistant", "tool"]
    content: str
    citations: list
    message_seq: int
    created_at: datetime


class TurnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=20_000)


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    user_id: str
    session_id: str | None
    invocation_id: str
    tool: str
    args_digest: str
    scope: str
    status: str
    created_at: datetime
    decided_at: datetime | None


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    approve: bool


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    session_id: str | None
    run_id: str
    kind: str
    title: str
    content: str
    citations: list
    created_at: datetime
