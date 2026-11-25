"""add HY4 saved jobs and learning progress

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-25

HY4-C: users can save up to a few JDs for comparison and record progress on a
learning plan. Progress may only reference existing Evidence IDs; no new
fact tables are introduced here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="pasted"),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_hash", name="uq_saved_job_user_hash"),
    )
    op.create_index(op.f("ix_saved_jobs_user_id"), "saved_jobs", ["user_id"], unique=False)
    op.create_index(op.f("ix_saved_jobs_created_at"), "saved_jobs", ["created_at"], unique=False)

    op.create_table(
        "learning_progress",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("skill", sa.String(length=255), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="待开始"),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("actual_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "plan_id", "skill", "stage", name="uq_learning_progress_key"
        ),
    )
    op.create_index(
        op.f("ix_learning_progress_user_id"), "learning_progress", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_learning_progress_plan_id"), "learning_progress", ["plan_id"], unique=False
    )
    op.create_index(
        op.f("ix_learning_progress_created_at"),
        "learning_progress", ["created_at"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_learning_progress_created_at"), table_name="learning_progress")
    op.drop_index(op.f("ix_learning_progress_plan_id"), table_name="learning_progress")
    op.drop_index(op.f("ix_learning_progress_user_id"), table_name="learning_progress")
    op.drop_table("learning_progress")
    op.drop_index(op.f("ix_saved_jobs_created_at"), table_name="saved_jobs")
    op.drop_index(op.f("ix_saved_jobs_user_id"), table_name="saved_jobs")
    op.drop_table("saved_jobs")
