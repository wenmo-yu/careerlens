"""LLM-compiled Wiki pages and their revision history.

A WikiPage is a user-visible, source-grounded topic page compiled from
evidence. A WikiRevision is an immutable snapshot of the version that a write
replaced — mirroring WeKnora's wiki_page.go semantics:

- ``version`` bumps when content, status, or citations change; link bookkeeping
  does not bump it.
- ``edit_source`` on a revision records the author of the *superseded* version,
  not the writer performing the replacement.
- Rollback is expressed as an ordinary edit that happens to carry old content,
  never as a destructive overwrite of history.
- No database foreign keys, consistent with every other model here and with
  both the Alembic and ``create_all`` schema paths.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

EDIT_SOURCES = ("user", "agent", "pipeline", "revert")
PAGE_STATUSES = ("draft", "published", "archived")


class WikiPage(Base):
    __tablename__ = "wiki_pages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    page_type: Mapped[str] = mapped_column(String(50), nullable=False, default="concept")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_edit_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pipeline"
    )
    source_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    chunk_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    out_links: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    in_links: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="published")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_wiki_page_user_slug"),
    )


class WikiRevision(Base):
    __tablename__ = "wiki_page_revisions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    page_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    page_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    chunk_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Author of the version this snapshot replaces (WeKnora wiki_page.go:351).
    edit_source: Mapped[str] = mapped_column(String(20), nullable=False)
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("page_id", "version", name="uq_wiki_revision_page_version"),
    )
