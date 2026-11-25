"""HY4-D: self-reported assessments and constraints.

These records are explicitly NOT part of the fact profile. They are stored
separately, carry their own version/consent metadata, and must be exportable
and deletable. Assessment answers never change a skill coverage score.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AssessmentResult(Base):
    __tablename__ = "assessment_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    instrument: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[str] = mapped_column(String(30), nullable=False, default="v1")
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    answers_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="self_report")
    consent: Mapped[bool] = mapped_column(nullable=False, default=False)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        # Python-side default keeps microseconds; SQLite's CURRENT_TIMESTAMP is
        # second-resolution and would collide on a rapid retake (unique key below).
        default=lambda: datetime.now(UTC), server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "instrument", "version", "taken_at",
            name="uq_assessment_result_user_instrument_version_time",
        ),
        Index("ix_assessment_result_user_instrument", "user_id", "instrument"),
    )


class UserConstraint(Base):
    __tablename__ = "user_constraints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="self_report")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "kind", name="uq_user_constraint_user_kind"),
    )
