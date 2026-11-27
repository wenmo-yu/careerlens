import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AccountDeletionReceipt(Base):
    __tablename__ = "account_deletion_receipts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    deleted_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    vector_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DeletionWork(Base):
    """A durable cleanup target owned by a receipt, independent of tenant data."""

    __tablename__ = "deletion_work"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    receipt_id: Mapped[str | None] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(128))
    collection: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ready_at: Mapped[int] = mapped_column(BigInteger, default=0)
    lease_until: Mapped[int | None] = mapped_column(BigInteger)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    last_error: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (Index("ix_deletion_work_ready", "status", "ready_at"),)
