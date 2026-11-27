from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class JobAnalyzeRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    jd_text: str = Field(min_length=10, max_length=40_000)
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


class RequirementV2(BaseModel):
    id: str
    name: str
    category: Literal["skill", "qualification", "responsibility", "preference"]
    priority: Literal["required", "preferred"]
    raw_quote: str
    span_start: int
    span_end: int
    alternative_group: str | None = None


class MatchCoverage(BaseModel):
    method: Literal["requirement_coverage_v1"] = "requirement_coverage_v1"
    assessed_groups: int
    total_skill_groups: int
    coverage: float
    qualification_checks: list[dict[str, Any]]
