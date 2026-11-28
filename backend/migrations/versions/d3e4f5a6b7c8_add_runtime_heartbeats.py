"""Add liveness heartbeats for workflow worker and agent scheduler.

Revision chain: c7d8e9f0a1b2 -> this revision. Additive only.
"""

import sqlalchemy as sa
from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table("runtime_heartbeats"):
        return
    op.create_table(
        "runtime_heartbeats",
        sa.Column("role", sa.String(16), primary_key=True),
        sa.Column("instance_id", sa.String(36), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("heartbeat_at", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=False),
    )


def downgrade() -> None:
    if _has_table("runtime_heartbeats"):
        op.drop_table("runtime_heartbeats")
