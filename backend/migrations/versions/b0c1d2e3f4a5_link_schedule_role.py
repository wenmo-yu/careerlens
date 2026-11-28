"""Link durable schedules to roles and record the role version per occurrence.

Revision chain: a9b0c1d2e3f4 -> this revision. Additive only; existing rows get
NULL role_id/role_version and keep using the schedule's own prompt.
"""

import sqlalchemy as sa
from alembic import op

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_column("agent_schedules", "role_id"):
        op.add_column("agent_schedules", sa.Column("role_id", sa.String(36), nullable=True))
        op.create_index("ix_agent_schedules_role_id", "agent_schedules", ["role_id"])
    if not _has_column("agent_schedule_occurrences", "role_version"):
        op.add_column(
            "agent_schedule_occurrences", sa.Column("role_version", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    if _has_column("agent_schedule_occurrences", "role_version"):
        op.drop_column("agent_schedule_occurrences", "role_version")
    if _has_column("agent_schedules", "role_id"):
        op.drop_index("ix_agent_schedules_role_id", "agent_schedules")
        op.drop_column("agent_schedules", "role_id")
