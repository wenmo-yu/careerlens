"""A structure-aware, locatable chunk parsed from one SourceDocument.

This is the common contract for the three-phase plan: phase one produces these
blocks, phase two's Wiki references and phase three's event sourcing anchor on
``evidence_id``. Fields mirror WeKnora's source_blocks (start/end/locator) and
document-revision idioms.

Key invariants:
- ``evidence_id`` is stable for the lifetime of the block — Wiki references and
  future event sourcing use it as the anchor, never a regenerated value.
- location fields (page/bbox/time/section) are persisted — returning the user
  to the exact origin of a multi-format upload is the product core.
- ``content_hash`` is the evidence-level dedup key (``user_id + content_hash``);
  multiple sources contributing identical text keep one evidence row but all
  keep their own ParsedBlock with the original location.
- ``content_revision`` is reserved for the phase-three stale-task guard.
- No database foreign keys (see SourceDocument docstring).
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ParsedBlock(Base):
    __tablename__ = "parsed_blocks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    evidence_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    doc_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    time_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    section_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    __table_args__ = (
        UniqueConstraint("doc_id", "block_index", name="uq_parsed_block_doc_index"),
        Index("ix_parsed_block_user_hash", "user_id", "content_hash"),
        Index("ix_parsed_block_evidence", "user_id", "evidence_id"),
    )
