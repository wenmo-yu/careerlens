"""Request bodies for self-reported assessments and profile extensions.

Kept in ``schemas`` rather than inline in the route module so validation rules
are importable by tests and future clients without pulling in FastAPI routing.
"""

from pydantic import BaseModel, Field


class AssessmentSubmit(BaseModel):
    """Legacy quick form: work preference, six-item RIASEC, or a free-text label."""

    user_id: str = Field(min_length=1, max_length=128)
    instrument: str = Field(min_length=1, max_length=50)
    answers: dict[str, int] = Field(default_factory=dict)
    label: str | None = Field(default=None, max_length=50)
    consent: bool = False


class InstrumentSubmit(BaseModel):
    """Versioned item pack submission; completeness is checked by the scorer."""

    user_id: str = Field(min_length=1, max_length=128)
    answers: dict[str, int] = Field(default_factory=dict)
    consent: bool = False


class ConstraintUpsert(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=1, max_length=1000)
    strength: int = Field(default=1, ge=1, le=5)


class DimensionToggle(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=1000)
    enabled: bool = True
    value: dict[str, object] | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ViewPreferences(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    mode: str = Field(default="job_search", max_length=40)
    modules: dict[str, bool] = Field(default_factory=dict)


class InterviewStory(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    situation: str = Field(default="", max_length=2000)
    action: str = Field(default="", max_length=2000)
    result: str = Field(default="", max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list)
