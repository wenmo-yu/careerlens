"""Durable agent schedules and idempotent due occurrences (M8).

A schedule is an internal task planner, not an external automation. It can only
submit an ordinary agent run for the same user; revoked tokens and disabled
schedules stop it. One occurrence is unique per (schedule_id, due_at).
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SCHEDULE_STATES = ("active", "paused", "disabled")
OCCURRENCE_STATES = ("pending", "claimed", "succeeded", "skipped", "failed")


class AgentSchedule(Base):
    __tablename__ = "agent_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    misfire_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="skip")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    actor_token_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Optional durable role: when set, triggers run with that role's prompt and
    # frozen tool allowlist (M8 role-schedule linkage).
    role_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    next_due: Mapped[int] = mapped_column(Integer, nullable=False)
    last_occurrence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('active','paused','disabled')", name="ck_agent_schedule_state"
        ),
        CheckConstraint(
            "misfire_policy IN ('skip','run_once')", name="ck_agent_schedule_misfire"
        ),
        Index("ix_agent_schedule_due", "state", "next_due"),
    )


class AgentScheduleOccurrence(Base):
    __tablename__ = "agent_schedule_occurrences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    schedule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    due_at: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # The exact role version used by this occurrence, for audit.
    role_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("schedule_id", "due_at", name="uq_agent_schedule_occurrence"),
        CheckConstraint(
            "status IN ('pending','claimed','succeeded','skipped','failed')",
            name="ck_agent_occurrence_status",
        ),
        Index("ix_agent_occurrence_due", "status", "due_at"),
    )
