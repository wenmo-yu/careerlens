"""Original uploaded document and its parse lifecycle.

A SourceDocument is the durable record of one raw upload. Its ``source_hash``
(sha256 of the raw bytes) is the file-level identity used for idempotent
re-uploads; the block-level ``content_hash`` lives on ParsedBlock for evidence
deduplication. No database foreign keys are used — relationships are string ids
plus application-level checks, consistent with every other model here and
compatible with both the Alembic and ``create_all`` schema paths.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(20), nullable=False, default="parsed")
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "source_hash", name="uq_source_doc_user_hash"),
        Index("ix_source_doc_user_created", "user_id", "created_at"),
    )
