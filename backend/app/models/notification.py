"""Read receipts for the in-app notification centre (M8).

Notification content is derived from real durable facts (approvals, runs,
tasks, schedules); only the user's read state is persisted here. There is no
delivery, no external destination and no second source of truth.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentNotificationRead(Base):
    __tablename__ = "agent_notification_reads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Stable key of the derived fact, e.g. "approval:<id>" or "run_failed:<id>".
    fact_key: Mapped[str] = mapped_column(String(200), nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "fact_key", name="uq_agent_notification_read"),
        Index("ix_agent_notification_user", "user_id", "read_at"),
    )
