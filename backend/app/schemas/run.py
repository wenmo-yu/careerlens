from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

RunOperation = Literal["job_analysis", "report", "wiki_compile", "file_import", "media_import"]
RunStatus = Literal[
    "queued", "running", "waiting_confirmation", "succeeded", "failed", "cancelled", "interrupted"
]


class JobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    jd_text: str = Field(min_length=10, max_length=40_000)
    weekly_hours: int = Field(default=10, ge=1, le=80)


class WikiInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=255, pattern=r"^[\w-]+$")
    title: str = Field(min_length=1, max_length=255)
    evidence_ids: list[Annotated[str, Field(min_length=1, max_length=36)]] = Field(
        min_length=1, max_length=50
    )
    base_version: int | None = Field(default=None, ge=1)


class ReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_analysis_id: str = Field(min_length=1, max_length=36)


class StartRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
    requires_confirmation: bool = False


class StartJob(StartRun):
    operation: Literal["job_analysis"]
    input: JobInput


class StartWiki(StartRun):
    operation: Literal["wiki_compile"]
    input: WikiInput


class StartReport(StartRun):
    operation: Literal["report"]
    input: ReportInput


RunCreate = Annotated[StartJob | StartWiki | StartReport, Field(discriminator="operation")]


class RunDecision(BaseModel):
    approve: bool


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    operation: RunOperation
    status: RunStatus
    confirmation: str
    attempts: int
    event_seq: int
    result: dict | None
    error_code: str | None
    created_at: datetime


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    status: str
    attempt: int
    updated_at: datetime


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    schema_version: Literal[1] = 1
    run_id: str
    seq: int
    generation: int
    event_type: str
    data: dict
    created_at: datetime
