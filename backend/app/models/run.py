from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_token_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, deferred=True)
    upload_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    confirmation: Mapped[str] = mapped_column(String(16), default="none")
    fencing_token: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    lease_owner: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    input_epoch: Mapped[int] = mapped_column(Integer, default=0)
    target_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    target_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_seq: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_run_user_request_key"),
        CheckConstraint(
            "status IN ('queued','running','waiting_confirmation','succeeded',"
            "'failed','cancelled','interrupted')",
            name="ck_run_status",
        ),
        Index("ix_run_queue", "status", "created_at", "id"),
        Index("ix_run_leases", "status", "lease_until"),
        Index("ix_run_user_queue", "user_id", "created_at", "id"),
    )


class RunScope(Base):
    __tablename__ = "run_scopes"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("ix_run_scope_user", "user_id"),)


class RunStep(Base):
    __tablename__ = "run_steps"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(16))
    attempt: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunEvent(Base):
    __tablename__ = "run_events"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    generation: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceIndexWork(Base):
    __tablename__ = "evidence_index_work"

    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(8))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ready_at: Mapped[int] = mapped_column(BigInteger, default=0, index=True)
