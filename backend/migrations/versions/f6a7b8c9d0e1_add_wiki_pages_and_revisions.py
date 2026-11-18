"""add wiki pages and revisions

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-18

Phase two knowledge organization: compiled, source-grounded topic pages with
an immutable revision history. Version bumps only on user-visible content
changes; revisions snapshot the superseded version's author and content.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wiki_pages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("page_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("last_edit_source", sa.String(length=20), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("chunk_refs", sa.JSON(), nullable=False),
        sa.Column("out_links", sa.JSON(), nullable=False),
        sa.Column("in_links", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "slug", name="uq_wiki_page_user_slug"),
    )
    op.create_index(op.f("ix_wiki_pages_user_id"), "wiki_pages", ["user_id"], unique=False)

    op.create_table(
        "wiki_page_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("page_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("page_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("edit_source", sa.String(length=20), nullable=False),
        sa.Column(
            "edited_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "page_id", "version", name="uq_wiki_revision_page_version"
        ),
    )
    for column in ("page_id", "user_id"):
        op.create_index(
            op.f(f"ix_wiki_page_revisions_{column}"),
            "wiki_page_revisions",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in ("user_id", "page_id"):
        op.drop_index(
            op.f(f"ix_wiki_page_revisions_{column}"), table_name="wiki_page_revisions"
        )
    op.drop_table("wiki_page_revisions")
    op.drop_index(op.f("ix_wiki_pages_user_id"), table_name="wiki_pages")
    op.drop_table("wiki_pages")
