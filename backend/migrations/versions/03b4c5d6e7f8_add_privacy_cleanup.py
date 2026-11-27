"""Persist cleanup work and preserve safe history around a privacy deletion."""

import sqlalchemy as sa
from alembic import op

revision = "03b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in ("career_reports", "wiki_pages"):
        if "privacy_redacted" not in {item["name"] for item in inspector.get_columns(table)}:
            op.add_column(table, sa.Column(
                "privacy_redacted", sa.Boolean(), nullable=False, server_default=sa.false(),
            ))
    messages = {item["name"] for item in inspector.get_columns("conversation_messages")}
    if "evidence_ids" not in messages:
        op.add_column("conversation_messages", sa.Column("evidence_ids", sa.JSON(), nullable=True))
    if inspector.has_table("deletion_work"):
        return
    op.create_table(
        "deletion_work",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("receipt_id", sa.String(36)),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("subject", sa.String(128)),
        sa.Column("collection", sa.String(255)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("ready_at", sa.BigInteger(), nullable=False),
        sa.Column("lease_until", sa.BigInteger()),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("last_error", sa.String(80)),
    )
    op.create_index("ix_deletion_work_receipt_id", "deletion_work", ["receipt_id"])
    op.create_index("ix_deletion_work_ready", "deletion_work", ["status", "ready_at"])


def downgrade() -> None:
    raise RuntimeError("Restore a pre-upgrade backup instead of removing deletion tracking")
