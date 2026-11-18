"""Tombstone for profile items the user explicitly removed.

Without this, rebuilding the profile re-extracts a removed item from the
original evidence, undoing the user's correction. A suppression record keeps
the removal durable across rebuilds. No database foreign keys (see the other
models): identity is (user_id, category, normalized name).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProfileSuppression(Base):
    __tablename__ = "profile_suppressions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "category", "name", name="uq_profile_suppression"),
    )
