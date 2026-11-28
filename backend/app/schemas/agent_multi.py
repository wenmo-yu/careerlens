from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChildTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["researcher", "reviewer", "synthesizer"]
    input: str = Field(min_length=1, max_length=20_000)


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(default="default", max_length=36)
    title: str = Field(min_length=1, max_length=200)
    children: list[ChildTaskInput] = Field(min_length=1, max_length=3)
    max_turns: int = Field(default=6, ge=1, le=12)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    workspace_id: str
    team_id: str
    parent_id: str | None
    role: str
    title: str
    input: str
    status: str
    budget: dict[str, Any]
    result: dict[str, Any]
    session_id: str | None
    run_id: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class TaskRetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)


class TeamMailCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    message_key: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list, max_length=50)
    recipient_task_id: str | None = None


class TeamMailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    team_id: str
    sender_task_id: str | None
    recipient_task_id: str | None
    message_key: str
    payload: dict[str, Any]
    citations: list[str]
    created_at: datetime


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(default="default", max_length=36)
    name: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=20_000)
    interval_seconds: int = Field(default=3600, ge=60, le=2_592_000)
    misfire_policy: Literal["skip", "run_once"] = "skip"
    start_at: int | None = None
    role_id: str | None = Field(default=None, max_length=36)


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    workspace_id: str
    name: str
    prompt: str
    interval_seconds: int
    timezone: str
    misfire_policy: str
    state: str
    role_id: str | None
    next_due: int
    last_occurrence: int | None
    created_at: datetime
    updated_at: datetime


class ScheduleStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    state: Literal["active", "paused", "disabled"]


class ScheduleOccurrenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schedule_id: str
    due_at: int
    status: str
    run_id: str | None
    role_version: int | None
    reason: str | None
    created_at: datetime
