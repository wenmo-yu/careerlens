"""HY4-B: read-only, explainable profile aggregation.

These numbers are descriptors of stored Evidence and ProfileItem rows, not
new facts about the user. Every field carries a methodology note so the UI can
show what the number means and what it does not.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class CoverageRead(BaseModel):
    supported: int = 0
    weak: int = 0
    missing: int = 0


class AssessmentHighlight(BaseModel):
    instrument: str
    title: str | None = None
    version: str
    code: str | None = None
    taken_at: datetime
    note: str = "自陈探索结果，不是能力事实，不进入岗位匹配分。"


class ProfileOverviewRead(BaseModel):
    user_id: str
    evidence_count: int = 0
    source_document_count: int = 0
    readable_evidence_count: int = 0
    profile_item_count: int = 0
    confirmed_item_count: int = 0
    unconfirmed_item_count: int = 0
    self_report_item_count: int = 0
    coverage: CoverageRead = Field(default_factory=CoverageRead)
    by_category: dict[str, int] = Field(default_factory=dict)
    assessments: list[AssessmentHighlight] = Field(default_factory=list)
    generated_at: datetime
    methodology: str = (
        "独立证据按 Evidence 行计；同一文本来自多个来源仍只算一条。"
        "supported=有有效证据且非弱证据；weak=仅一条证据或置信度<0.7；"
        "missing=无任何有效证据。用户确认只代表认可表述，不代表自动成为事实。"
        "assessments 只回显最近一次自陈结果，不参与任何匹配分。"
    )
