"""HY4-C: saved JDs and learning progress.

Both are user-owned records. They never create new facts: progress can only
reference an existing Evidence ID, and saved JDs are raw user-provided text.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="pasted")
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "source_hash", name="uq_saved_job_user_hash"),
        Index("ix_saved_job_user_created", "user_id", "created_at"),
    )


class LearningProgress(Base):
    __tablename__ = "learning_progress"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    skill: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="待开始")
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    actual_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "plan_id", "skill", "stage", name="uq_learning_progress_key"),
        Index("ix_learning_progress_user_plan", "user_id", "plan_id"),
    )
