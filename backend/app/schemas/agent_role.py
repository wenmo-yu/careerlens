from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(default="default", max_length=36)
    name: str = Field(min_length=1, max_length=120)
    template: Literal[
        "evidence_researcher",
        "job_analyst",
        "learning_planner",
        "evidence_reviewer",
        "career_coach",
    ]
    prompt: str | None = Field(default=None, max_length=20_000)
    tool_allowlist: list[str] | None = Field(default=None, max_length=20)
    model_policy: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    prompt: str | None = Field(default=None, max_length=20_000)
    tool_allowlist: list[str] | None = Field(default=None, max_length=20)
    model_policy: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class RoleStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    state: Literal["active", "paused", "archived"]


class RoleTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=20_000)


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    workspace_id: str
    name: str
    template: str
    version: int
    prompt: str
    tool_allowlist: list[str]
    model_policy: dict[str, Any]
    budget: dict[str, Any]
    output_schema: dict[str, Any]
    state: str
    session_id: str | None
    created_at: datetime
    updated_at: datetime
