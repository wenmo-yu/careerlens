"""Preserve parsed locations, deduplicate writes, and version Wiki citations."""

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE evidence SET content_hash = NULL WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY user_id, content_hash ORDER BY created_at, id
                ) AS position FROM evidence WHERE content_hash IS NOT NULL
            ) AS ranked WHERE position > 1
        )
        """
    )
    op.drop_index("ix_evidence_user_hash", table_name="evidence")
    op.create_index("ix_evidence_user_hash", "evidence", ["user_id", "content_hash"], unique=True)
    with op.batch_alter_table("parsed_blocks") as batch:
        batch.alter_column("evidence_id", existing_type=sa.String(36), nullable=True)
    op.add_column("wiki_page_revisions", sa.Column("source_refs", sa.JSON(), nullable=True))
    op.add_column("wiki_page_revisions", sa.Column("chunk_refs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("wiki_page_revisions", "chunk_refs")
    op.drop_column("wiki_page_revisions", "source_refs")
    op.execute("DELETE FROM parsed_blocks WHERE evidence_id IS NULL")
    with op.batch_alter_table("parsed_blocks") as batch:
        batch.alter_column("evidence_id", existing_type=sa.String(36), nullable=False)
    op.drop_index("ix_evidence_user_hash", table_name="evidence")
    op.create_index("ix_evidence_user_hash", "evidence", ["user_id", "content_hash"])
