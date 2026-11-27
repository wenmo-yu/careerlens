"""Add the agent plane: sessions, messages, runtime slots, approvals, run kind."""

import sqlalchemy as sa
from alembic import op

revision = "a9b8c7d6e5f4"
down_revision = "14c5d6e7f8a9"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("agent_runs")}
    if "executor_kind" not in columns:
        op.add_column(
            "agent_runs",
            sa.Column("executor_kind", sa.String(16), nullable=False, server_default="workflow"),
        )
    if "session_id" not in columns:
        op.add_column("agent_runs", sa.Column("session_id", sa.String(36), nullable=True))
        op.create_index("ix_agent_runs_session_id", "agent_runs", ["session_id"])

    if not _has_table("agent_sessions"):
        op.create_table(
            "agent_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=False, server_default="default"),
            sa.Column("title", sa.String(200), nullable=False, server_default=""),
            sa.Column("head_revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("runtime_generation", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint("status IN ('active','closed')", name="ck_agent_session_status"),
        )
        op.create_index("ix_agent_sessions_user_id", "agent_sessions", ["user_id"])
        op.create_index("ix_agent_session_user", "agent_sessions", ["user_id", "created_at"])

    if not _has_table("agent_session_messages"):
        op.create_table(
            "agent_session_messages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("session_id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("run_id", sa.String(36), nullable=True),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("citations", sa.JSON(), nullable=False),
            sa.Column("message_seq", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("session_id", "message_seq", name="uq_agent_message_seq"),
            sa.CheckConstraint(
                "role IN ('user','assistant','tool')", name="ck_agent_message_role"
            ),
        )
        op.create_index(
            "ix_agent_session_messages_session_id", "agent_session_messages", ["session_id"]
        )
        op.create_index("ix_agent_session_messages_user_id", "agent_session_messages", ["user_id"])
        op.create_index("ix_agent_session_messages_run_id", "agent_session_messages", ["run_id"])
        op.create_index(
            "ix_agent_message_history", "agent_session_messages", ["session_id", "message_seq"]
        )

    if not _has_table("agent_runtime_slots"):
        op.create_table(
            "agent_runtime_slots",
            sa.Column("slot_id", sa.String(36), primary_key=True),
            sa.Column("state", sa.String(16), nullable=False, server_default="spawning"),
            sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("session_id", sa.String(36), nullable=True),
            sa.Column("run_id", sa.String(36), nullable=True),
            sa.Column("pid", sa.Integer(), nullable=True),
            sa.Column("fencing_token", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("lease_owner", sa.String(36), nullable=True),
            sa.Column("lease_until", sa.BigInteger(), nullable=True),
            sa.Column("restarts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "state_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()
            ),
            sa.Column("diagnostics", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint(
                "state IN ('spawning','warm','binding','ready','running','waiting',"
                "'draining','faulted','terminated')",
                name="ck_agent_slot_state",
            ),
        )
        op.create_index("ix_agent_runtime_slots_session_id", "agent_runtime_slots", ["session_id"])
        op.create_index("ix_agent_runtime_slots_run_id", "agent_runtime_slots", ["run_id"])
        op.create_index("ix_agent_slot_state", "agent_runtime_slots", ["state", "state_changed_at"])

    if not _has_table("agent_approvals"):
        op.create_table(
            "agent_approvals",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("run_id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("session_id", sa.String(36), nullable=True),
            sa.Column("invocation_id", sa.String(64), nullable=False),
            sa.Column("tool", sa.String(64), nullable=False),
            sa.Column("args_digest", sa.String(64), nullable=False),
            sa.Column("scope", sa.String(100), nullable=False, server_default=""),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("decision_by", sa.String(128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("run_id", "invocation_id", name="uq_agent_approval_invocation"),
            sa.CheckConstraint(
                "status IN ('pending','approved','denied','expired')",
                name="ck_agent_approval_status",
            ),
        )
        op.create_index("ix_agent_approvals_run_id", "agent_approvals", ["run_id"])
        op.create_index("ix_agent_approvals_user_id", "agent_approvals", ["user_id"])
        op.create_index(
            "ix_agent_approval_pending", "agent_approvals", ["user_id", "status", "created_at"]
        )

    # Replace the one-running-run-per-user index with a workflow-only predicate.
    op.drop_index("uq_running_run_user", table_name="agent_runs")
    op.create_index(
        "uq_running_run_user",
        "agent_runs",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("status = 'running' AND executor_kind = 'workflow'"),
        postgresql_where=sa.text("status = 'running' AND executor_kind = 'workflow'"),
    )


def downgrade() -> None:
    raise RuntimeError("Restore a backup instead of removing the agent plane")
