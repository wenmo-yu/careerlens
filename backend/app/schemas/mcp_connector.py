from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConnectorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(default="default", max_length=36)
    namespace: str = Field(min_length=3, max_length=64)
    allowed_tools: list[str] = Field(min_length=1, max_length=50)
    required_scope: Literal["read", "write", "manage"] = "read"


class ConnectorStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    state: Literal["registered", "enabled", "disabled"]


class ConnectorAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)


class AdmissionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    qualified_name: str = Field(min_length=1, max_length=200)
    config_digest: str | None = Field(default=None, max_length=64)


class ConnectorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    workspace_id: str
    namespace: str
    allowed_tools: list[str]
    required_scope: str
    config_digest: str
    state: str
    revoked: bool
    created_at: datetime
    updated_at: datetime


class RevokeRead(BaseModel):
    revoked: bool
    state: str


class AdmissionResult(BaseModel):
    allowed: bool
    reason: str
