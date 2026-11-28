"""Add multi-agent task trees and durable schedules.

Revision chain: a9b8c7d6e5f4 -> b5c6d7e8f9a0 (M5 ledger) -> this revision.
Both additions are additive: existing runs and workflows are untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("agent_tasks"):
        op.create_table(
            "agent_tasks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=False, server_default="default"),
            sa.Column("team_id", sa.String(36), nullable=False),
            sa.Column("parent_id", sa.String(36), nullable=True),
            sa.Column("role", sa.String(32), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("input", sa.Text(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
            sa.Column("budget", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("result", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("session_id", sa.String(36), nullable=True),
            sa.Column("run_id", sa.String(36), nullable=True),
            sa.Column("error", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint(
                "status IN ('queued','running','waiting','succeeded','failed','cancelled')",
                name="ck_agent_task_status",
            ),
            sa.UniqueConstraint(
                "team_id", "role", "parent_id", name="uq_agent_task_team_role_parent"
            ),
            sa.ForeignKeyConstraint(["parent_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_agent_tasks_user_id", "agent_tasks", ["user_id"])
        op.create_index("ix_agent_tasks_team_id", "agent_tasks", ["team_id"])
        op.create_index("ix_agent_tasks_session_id", "agent_tasks", ["session_id"])
        op.create_index("ix_agent_tasks_run_id", "agent_tasks", ["run_id"])
        op.create_index("ix_agent_task_parent", "agent_tasks", ["parent_id", "status"])

    if not _has_table("agent_team_messages"):
        op.create_table(
            "agent_team_messages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("team_id", sa.String(36), nullable=False),
            sa.Column("task_id", sa.String(36), nullable=True),
            sa.Column("sender_task_id", sa.String(36), nullable=True),
            sa.Column("recipient_task_id", sa.String(36), nullable=True),
            sa.Column("message_key", sa.String(128), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("citations", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("team_id", "message_key", name="uq_agent_team_message_key"),
            sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_agent_team_messages_team_id", "agent_team_messages", ["team_id"])
        op.create_index("ix_agent_team_messages_task_id", "agent_team_messages", ["task_id"])
        op.create_index(
            "ix_agent_team_messages_recipient_task_id",
            "agent_team_messages",
            ["recipient_task_id"],
        )
        op.create_index(
            "ix_agent_team_mail",
            "agent_team_messages",
            ["team_id", "recipient_task_id", "created_at"],
        )

    if not _has_table("agent_task_budget_use"):
        op.create_table(
            "agent_task_budget_use",
            sa.Column("task_id", sa.String(36), primary_key=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("last_run_id", sa.String(36), nullable=True),
            sa.Column("last_attempt", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        )

    if not _has_table("agent_schedules"):
        op.create_table(
            "agent_schedules",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=False, server_default="default"),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("interval_seconds", sa.Integer(), nullable=False),
            sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
            sa.Column("misfire_policy", sa.String(16), nullable=False, server_default="skip"),
            sa.Column("state", sa.String(16), nullable=False, server_default="active"),
            sa.Column("actor_token_id", sa.String(36), nullable=True),
            sa.Column("next_due", sa.Integer(), nullable=False),
            sa.Column("last_occurrence", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint(
                "state IN ('active','paused','disabled')", name="ck_agent_schedule_state"
            ),
            sa.CheckConstraint(
                "misfire_policy IN ('skip','run_once')", name="ck_agent_schedule_misfire"
            ),
        )
        op.create_index("ix_agent_schedules_user_id", "agent_schedules", ["user_id"])
        op.create_index(
            "ix_agent_schedule_due", "agent_schedules", ["state", "next_due"]
        )

    if not _has_table("agent_schedule_occurrences"):
        op.create_table(
            "agent_schedule_occurrences",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("schedule_id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(128), nullable=False),
            sa.Column("due_at", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("run_id", sa.String(36), nullable=True),
            sa.Column("reason", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint(
                "schedule_id", "due_at", name="uq_agent_schedule_occurrence"
            ),
            sa.CheckConstraint(
                "status IN ('pending','claimed','succeeded','skipped','failed')",
                name="ck_agent_occurrence_status",
            ),
        )
        op.create_index(
            "ix_agent_schedule_occurrences_schedule_id",
            "agent_schedule_occurrences",
            ["schedule_id"],
        )
        op.create_index(
            "ix_agent_schedule_occurrences_user_id", "agent_schedule_occurrences", ["user_id"]
        )
        op.create_index(
            "ix_agent_schedule_occurrences_run_id", "agent_schedule_occurrences", ["run_id"]
        )
        op.create_index(
            "ix_agent_occurrence_due", "agent_schedule_occurrences", ["status", "due_at"]
        )


def downgrade() -> None:
    for name in (
        "agent_schedule_occurrences",
        "agent_schedules",
        "agent_task_budget_use",
        "agent_team_messages",
        "agent_tasks",
    ):
        if _has_table(name):
            op.drop_table(name)
