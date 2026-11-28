"""Add durable long-lived agent roles (M8 role lifecycle).

Revision chain: d3e4f5a6b7c8 -> this revision. Additive only: existing runs,
schedules and task trees are untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("agent_roles"):
        op.create_table(
            "agent_roles",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=False, server_default="default"),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("template", sa.String(48), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("tool_allowlist", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("model_policy", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("budget", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("output_schema", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("state", sa.String(16), nullable=False, server_default="active"),
            sa.Column("session_id", sa.String(36), nullable=True),
            sa.Column("actor_token_id", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint(
                "state IN ('active','paused','archived')", name="ck_agent_role_state"
            ),
            sa.UniqueConstraint("user_id", "name", name="uq_agent_role_user_name"),
        )
        op.create_index("ix_agent_roles_user_id", "agent_roles", ["user_id"])
        op.create_index("ix_agent_roles_session_id", "agent_roles", ["session_id"])
        op.create_index("ix_agent_role_user", "agent_roles", ["user_id", "state"])


def downgrade() -> None:
    if _has_table("agent_roles"):
        op.drop_table("agent_roles")
