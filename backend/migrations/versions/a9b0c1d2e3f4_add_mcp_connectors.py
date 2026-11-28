"""Add MCP connector admission records (M8 policy layer).

Revision chain: f8a9b0c1d2e3 -> this revision. Additive only.
"""

import sqlalchemy as sa
from alembic import op

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("agent_mcp_connectors"):
        op.create_table(
            "agent_mcp_connectors",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=False, server_default="default"),
            sa.Column("namespace", sa.String(64), nullable=False),
            sa.Column("allowed_tools", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("required_scope", sa.String(32), nullable=False, server_default="read"),
            sa.Column("config_digest", sa.String(64), nullable=False),
            sa.Column("state", sa.String(16), nullable=False, server_default="registered"),
            sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint(
                "user_id", "namespace", name="uq_agent_mcp_connector_user_ns"
            ),
            sa.CheckConstraint(
                "state IN ('registered','enabled','disabled')",
                name="ck_agent_mcp_connector_state",
            ),
        )
        op.create_index(
            "ix_agent_mcp_connectors_user_id", "agent_mcp_connectors", ["user_id"]
        )
        op.create_index(
            "ix_agent_mcp_connector_user", "agent_mcp_connectors", ["user_id", "state"]
        )


def downgrade() -> None:
    if _has_table("agent_mcp_connectors"):
        op.drop_table("agent_mcp_connectors")
