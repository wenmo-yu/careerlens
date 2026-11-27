from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvalEvidence(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=16_000)
    source_type: str = "benchmark"
    source_name: str = "annotated-sample"


class EvalProfileLabel(BaseModel):
    category: str
    name: str


class EvalRetrievalQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    relevant_evidence_ids: list[str] = Field(min_length=1, max_length=100)


class EvalRequirementLabel(BaseModel):
    name: str
    status: str = Field(pattern="^(strong|partial|gap)$")


class EvalCase(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    evidence: list[EvalEvidence] = Field(min_length=1, max_length=100)
    expected_profile: list[EvalProfileLabel] = Field(default_factory=list, max_length=100)
    retrieval_queries: list[EvalRetrievalQuery] = Field(default_factory=list, max_length=40)
    jd_text: str = Field(default="", max_length=40_000)
    expected_requirements: list[EvalRequirementLabel] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_case_references(self):
        ids = {item.id for item in self.evidence}
        if len(ids) != len(self.evidence):
            raise ValueError("Evidence IDs must be unique within each case")
        for query in self.retrieval_queries:
            refs = set(query.relevant_evidence_ids)
            if len(refs) != len(query.relevant_evidence_ids) or not refs <= ids:
                raise ValueError("Relevant IDs must uniquely refer to evidence in the same case")
        return self


class EvaluationDataset(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    recall_k: int = Field(default=5, ge=1, le=20)
    cases: list[EvalCase] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_dataset_budget(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Case IDs must be unique")
        total = sum(
            len(case.jd_text) + sum(len(item.content) for item in case.evidence)
            + sum(len(item.query) for item in case.retrieval_queries)
            for case in self.cases
        )
        if total > 2_000_000 or sum(len(case.evidence) for case in self.cases) > 2000:
            raise ValueError("Dataset exceeds the evaluation budget")
        return self


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
