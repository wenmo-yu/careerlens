"""Wake reconciliation reports (M8 sleep/misfire strategy).

A report records what the service observed about a gap in scheduler liveness
and how many due occurrences were reconciled. It is diagnostic evidence, not a
business fact; the runs/occurrences remain the source of truth.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentWakeReport(Base):
    __tablename__ = "agent_wake_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    observed_gap_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    missed_due: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triggered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(String(64), nullable=False, default="wake_reconcile")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
