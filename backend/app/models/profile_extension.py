"""HY4-D: user-selected profile dimensions.

These tables extend the profile without polluting the five existing
ProfileItem.category values. Disabled dimensions are ignored by the UI and by
recommendations; they never become match-score inputs.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DimensionDefinition(Base):
    __tablename__ = "dimension_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="self_report")
    enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_dimension_user_key"),
        Index("ix_dimension_user_enabled", "user_id", "enabled"),
    )


class ProfileExtension(Base):
    __tablename__ = "profile_extensions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    dimension_key: Mapped[str] = mapped_column(String(80), nullable=False)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="self_report")
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "dimension_key", name="uq_profile_extension_user_dimension"),
        Index("ix_profile_extension_user_dimension", "user_id", "dimension_key"),
    )
