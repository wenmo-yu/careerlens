import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
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
