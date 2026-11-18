import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_evidence_source", "user_id", "source_type"),
        Index("ix_evidence_user_created", "user_id", "created_at"),
        Index("ix_evidence_user_hash", "user_id", "content_hash"),
    )
