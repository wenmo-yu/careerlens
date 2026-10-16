from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvalEvidence(BaseModel):
    id: str
    content: str
    source_type: str = "benchmark"
    source_name: str = "annotated-sample"


class EvalProfileLabel(BaseModel):
    category: str
    name: str


class EvalRetrievalQuery(BaseModel):
    query: str
    relevant_evidence_ids: list[str] = Field(min_length=1)


class EvalRequirementLabel(BaseModel):
    name: str
    status: str = Field(pattern="^(strong|partial|gap)$")


class EvalCase(BaseModel):
    id: str
    evidence: list[EvalEvidence] = Field(min_length=1)
    expected_profile: list[EvalProfileLabel] = Field(default_factory=list)
    retrieval_queries: list[EvalRetrievalQuery] = Field(default_factory=list)
    jd_text: str = ""
    expected_requirements: list[EvalRequirementLabel] = Field(default_factory=list)


class EvaluationDataset(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    recall_k: int = Field(default=5, ge=1, le=20)
    cases: list[EvalCase] = Field(min_length=1, max_length=1000)


class RegressionThresholds(BaseModel):
    profile_extraction_f1: float = Field(default=0.95, ge=0, le=1)
    evidence_recall_at_k: float = Field(default=0.95, ge=0, le=1)
    supported_claim_rate: float = Field(default=0.95, ge=0, le=1)
    requirement_matching_f1: float = Field(default=0.95, ge=0, le=1)


class RegressionRequest(BaseModel):
    dataset: EvaluationDataset
    minimums: RegressionThresholds = Field(default_factory=RegressionThresholds)


class EvaluationRunRead(BaseModel):
    id: str
    dataset_name: str
    profile_extraction_f1: float
    evidence_recall_at_k: float
    supported_claim_rate: float
    requirement_matching_f1: float
    metrics: dict
    details: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegressionFailure(BaseModel):
    metric: str
    actual: float
    minimum: float
    delta: float


class RegressionResult(BaseModel):
    status: Literal["passed", "failed"]
    run: EvaluationRunRead
    minimums: RegressionThresholds
    failures: list[RegressionFailure]
