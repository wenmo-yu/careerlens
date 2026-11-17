import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_extraction_f1: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_recall_at_k: Mapped[float] = mapped_column(Float, nullable=False)
    supported_claim_rate: Mapped[float] = mapped_column(Float, nullable=False)
    requirement_matching_f1: Mapped[float] = mapped_column(Float, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
