"""add source documents and parsed blocks

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-18

Phase one data foundation: a durable record of each raw upload and its
structure-aware, locatable parsed blocks. These become the anchor for phase
two Wiki references and phase three event sourcing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("parse_status", sa.String(length=20), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_hash", name="uq_source_doc_user_hash"),
    )
    op.create_index(
        "ix_source_doc_user_created", "source_documents", ["user_id", "created_at"], unique=False
    )
    op.create_index(
        op.f("ix_source_documents_created_at"),
        "source_documents",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_source_documents_user_id"), "source_documents", ["user_id"], unique=False
    )

    op.create_table(
        "parsed_blocks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("evidence_id", sa.String(length=36), nullable=False),
        sa.Column("doc_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("time_start", sa.Float(), nullable=True),
        sa.Column("time_end", sa.Float(), nullable=True),
        sa.Column("section_path", sa.String(length=500), nullable=True),
        sa.Column("image_ref", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("content_revision", sa.Integer(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_id", "block_index", name="uq_parsed_block_doc_index"),
    )
    op.create_index(
        "ix_parsed_block_user_hash", "parsed_blocks", ["user_id", "content_hash"], unique=False
    )
    op.create_index(
        "ix_parsed_block_evidence", "parsed_blocks", ["user_id", "evidence_id"], unique=False
    )
    for column in ("created_at", "doc_id", "evidence_id", "user_id", "content_hash"):
        op.create_index(
            op.f(f"ix_parsed_blocks_{column}"), "parsed_blocks", [column], unique=False
        )


def downgrade() -> None:
    for column in ("content_hash", "user_id", "evidence_id", "doc_id", "created_at"):
        op.drop_index(op.f(f"ix_parsed_blocks_{column}"), table_name="parsed_blocks")
    op.drop_index("ix_parsed_block_evidence", table_name="parsed_blocks")
    op.drop_index("ix_parsed_block_user_hash", table_name="parsed_blocks")
    op.drop_table("parsed_blocks")

    for column in ("user_id", "created_at"):
        op.drop_index(op.f(f"ix_source_documents_{column}"), table_name="source_documents")
    op.drop_index("ix_source_doc_user_created", table_name="source_documents")
    op.drop_table("source_documents")
