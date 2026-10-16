from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobAnalyzeRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    jd_text: str = Field(min_length=10)
    weekly_hours: int = Field(default=10, ge=1, le=80)


class JobAnalysisRead(BaseModel):
    id: str
    user_id: str
    title: str
    jd_text: str
    score: float
    requirements: list[dict[str, Any]]
    matches: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    learning_path: list[dict[str, Any]]
    report: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
