"""Persistent contract for agent sessions, messages, runtime slots and approvals.

These tables hold the durable facts of the agent plane. The daemon owns
processes only; the scheduler owns leases and generation checks; FastAPI and
this schema own sessions, runs, events, messages and approvals.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
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

SLOT_STATES = (
    "spawning",
    "warm",
    "binding",
    "ready",
    "running",
    "waiting",
    "draining",
    "faulted",
    "terminated",
)
TERMINAL_SLOT_STATES = ("faulted", "terminated")


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    head_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Bumped when a session runtime is rebuilt. Old runtimes may not commit.
    runtime_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('active','closed')", name="ck_agent_session_status"),
        Index("ix_agent_session_user", "user_id", "created_at"),
    )


class AgentMessage(Base):
    __tablename__ = "agent_session_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    citations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Monotonic per session; the UI uses it as a stable history cursor.
    message_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("session_id", "message_seq", name="uq_agent_message_seq"),
        CheckConstraint(
            "role IN ('user','assistant','tool')", name="ck_agent_message_role"
        ),
        Index("ix_agent_message_history", "session_id", "message_seq"),
    )


class AgentRuntimeSlot(Base):
    __tablename__ = "agent_runtime_slots"

    slot_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="spawning")
    # Generation of the shell/session binding. A stale shell must not commit.
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    restarts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    diagnostics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "state IN ('spawning','warm','binding','ready','running','waiting',"
            "'draining','faulted','terminated')",
            name="ck_agent_slot_state",
        ),
        # A bound slot is never returned to the warm pool: session_id is the
        # binding marker and cannot be cleared without terminating the row.
        Index("ix_agent_slot_state", "state", "state_changed_at"),
    )


class AgentApproval(Base):
    __tablename__ = "agent_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    invocation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    args_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    decision_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "invocation_id", name="uq_agent_approval_invocation"),
        CheckConstraint(
            "status IN ('pending','approved','denied','expired')",
            name="ck_agent_approval_status",
        ),
        Index("ix_agent_approval_pending", "user_id", "status", "created_at"),
    )
