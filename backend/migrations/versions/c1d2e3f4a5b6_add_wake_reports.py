"""Add agent wake reconciliation reports (M8 sleep/misfire strategy).

Revision chain: b0c1d2e3f4a5 -> this revision. Additive only.
"""

import sqlalchemy as sa
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("agent_wake_reports"):
        op.create_table(
            "agent_wake_reports",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("observed_gap_seconds", sa.Integer(), nullable=False),
            sa.Column("missed_due", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("triggered", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reason", sa.String(64), nullable=False, server_default="wake_reconcile"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    if _has_table("agent_wake_reports"):
        op.drop_table("agent_wake_reports")
