"""add evidence content hash for source-level dedup

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-18

Phase one dedup: sha256 of normalized chunk text, keyed per user. No unique
constraint — identical text from multiple sources is merged into one Evidence
row with all sources retained in source_metadata["sources"].
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_evidence_user_hash", "evidence", ["user_id", "content_hash"], unique=False
    )
    op.create_index(op.f("ix_evidence_content_hash"), "evidence", ["content_hash"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_evidence_content_hash"), table_name="evidence")
    op.drop_index("ix_evidence_user_hash", table_name="evidence")
    op.drop_column("evidence", "content_hash")
