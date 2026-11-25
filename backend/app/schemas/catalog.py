"""HY4-C: read-only catalog + recommendation response models."""

from pydantic import BaseModel


class RoleTemplateRead(BaseModel):
    role_id: str
    name: str
    family: str
    typical_tasks: list[str]
    required_skills: list[str]
    nice_to_have: list[str]
    entry_evidence: list[str]
    growth_path: list[str]
    source_note: str


class CourseRead(BaseModel):
    course_id: str
    title: str
    skill: str
    level: str
    format: str
    provider: str
    estimated_hours: float
    cost: str
    prerequisites: list[str]
    url: str
    license: str
    language: str
    last_checked_at: str
    alternative_ids: list[str]
    verification: str


class RoleSuggestionRead(BaseModel):
    role_id: str
    name: str
    family: str
    matched_required: list[str]
    matched_nice_to_have: list[str]
    gaps: list[str]
    evidence_ids: list[str]
    reason: str
    typical_tasks: list[str]
    growth_path: list[str]
    source_note: str
    coverage: float


class LearningPlanStepRead(BaseModel):
    stage: int
    skill: str
    priority: str | None = None
    current_level: int | None = None
    target_level: int
    estimated_hours: float | None = None
    start_week: int | None = None
    weeks: int | None = None
    goal: str
    deliverables: list[str]
    source_evidence_ids: list[str] = []
    resources: list[dict]
    verification: str
    progress_status: str = "待开始"
