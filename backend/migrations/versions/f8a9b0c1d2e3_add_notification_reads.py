"""Add in-app notification read receipts (M8 experience package).

Revision chain: e7f8a9b0c1d2 -> this revision. Additive only.
"""

import sqlalchemy as sa
from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("agent_notification_reads"):
        op.create_table(
            "agent_notification_reads",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("fact_key", sa.String(200), nullable=False),
            sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "fact_key", name="uq_agent_notification_read"),
        )
        op.create_index(
            "ix_agent_notification_user", "agent_notification_reads", ["user_id", "read_at"]
        )


def downgrade() -> None:
    if _has_table("agent_notification_reads"):
        op.drop_table("agent_notification_reads")
