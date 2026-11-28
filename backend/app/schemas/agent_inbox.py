from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fact_key: str
    kind: Literal[
        "approval_pending",
        "run_failed",
        "task_failed",
        "schedule_skipped",
        "schedule_failed",
    ]
    title: str
    detail: str
    ref_id: str | None
    created_at: str | None
    read: bool


class MarkReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    fact_keys: list[str] = Field(min_length=1, max_length=50)


class MarkReadResult(BaseModel):
    added: int
