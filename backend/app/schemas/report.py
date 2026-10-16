from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CareerReportGenerateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    job_analysis_id: str = Field(min_length=1, max_length=36)


class CareerReportRead(BaseModel):
    id: str
    user_id: str
    job_analysis_id: str
    version: int
    title: str
    content: dict[str, Any]
    markdown: str
    model_diagnostics: dict[str, Any]
    is_stale: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
