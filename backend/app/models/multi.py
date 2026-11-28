"""Durable task-tree and team-mailbox models for the M6 agent plane.

A team has a parent task and role-scoped child tasks. Children get their own
agent session, so their histories never leak into each other. The parent sees
only a bounded projection of child results and verified citations.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TASK_STATES = ("queued", "running", "waiting", "succeeded", "failed", "cancelled")
TERMINAL_TASK_STATES = ("succeeded", "failed", "cancelled")


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    team_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    input: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    budget: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','waiting','succeeded','failed','cancelled')",
            name="ck_agent_task_status",
        ),
        UniqueConstraint("team_id", "role", "parent_id", name="uq_agent_task_team_role_parent"),
        Index("ix_agent_task_parent", "parent_id", "status"),
    )


class AgentTeamMessage(Base):
    __tablename__ = "agent_team_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    sender_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recipient_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    message_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    citations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("team_id", "message_key", name="uq_agent_team_message_key"),
        Index("ix_agent_team_mail", "team_id", "recipient_task_id", "created_at"),
    )


class AgentTaskBudgetUse(Base):
    """Cumulative budget use across attempts, keyed by task and provider token bucket."""

    __tablename__ = "agent_task_budget_use"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
