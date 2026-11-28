from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WakeReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_seen: int = Field(ge=0)
    now: int = Field(ge=0)


class WakeReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    observed_gap_seconds: int
    missed_due: int
    triggered: int
    skipped: int
    reason: str
    created_at: datetime
