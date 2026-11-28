"""Add a durable tool ledger and artifacts for approved write tools.

A write invocation is recorded before execution (pending) and updated only
after the artifact is committed (succeeded/failed/denied). The unique
(run_id, invocation_id) key makes replay safe; it does not authorize a second
execution with different arguments.
"""

import sqlalchemy as sa
from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("agent_tool_ledger"):
        op.create_table(
            "agent_tool_ledger",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("session_id", sa.String(36), nullable=True),
            sa.Column("run_id", sa.String(36), nullable=False),
            sa.Column("invocation_id", sa.String(64), nullable=False),
            sa.Column("tool", sa.String(64), nullable=False),
            sa.Column("args_digest", sa.String(64), nullable=False),
            sa.Column("approval_id", sa.String(36), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint(
                "run_id", "invocation_id", name="uq_agent_tool_ledger_invocation"
            ),
            sa.CheckConstraint(
                "status IN ('pending','succeeded','failed','denied','unknown')",
                name="ck_agent_tool_ledger_status",
            ),
        )
        op.create_index("ix_agent_tool_ledger_user_id", "agent_tool_ledger", ["user_id"])
        op.create_index("ix_agent_tool_ledger_session_id", "agent_tool_ledger", ["session_id"])
        op.create_index("ix_agent_tool_ledger_run_id", "agent_tool_ledger", ["run_id"])
        op.create_index(
            "ix_agent_tool_ledger_user", "agent_tool_ledger", ["user_id", "created_at"]
        )
        op.create_index(
            "ix_agent_tool_ledger_run", "agent_tool_ledger", ["run_id", "invocation_id"]
        )

    if not _has_table("agent_artifacts"):
        op.create_table(
            "agent_artifacts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("session_id", sa.String(36), nullable=True),
            sa.Column("run_id", sa.String(36), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False, server_default="career_note"),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("citations", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_agent_artifacts_user_id", "agent_artifacts", ["user_id"])
        op.create_index("ix_agent_artifacts_session_id", "agent_artifacts", ["session_id"])
        op.create_index("ix_agent_artifacts_run_id", "agent_artifacts", ["run_id"])
        op.create_index("ix_agent_artifact_user", "agent_artifacts", ["user_id", "created_at"])
        op.create_index("ix_agent_artifact_run", "agent_artifacts", ["run_id", "created_at"])


def downgrade() -> None:
    if _has_table("agent_artifacts"):
        op.drop_table("agent_artifacts")
    if _has_table("agent_tool_ledger"):
        op.drop_table("agent_tool_ledger")
