"""add conversation messages

Revision ID: a1b2c3d4e5f6
Revises: c603b5469069
Create Date: 2026-11-17

Persist chat turns so multi-turn context can be assembled from durable facts
rather than the single in-flight message.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "c603b5469069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("thread_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.String(length=8000), nullable=False),
        sa.Column("intent", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_msg_thread_created",
        "conversation_messages",
        ["thread_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_messages_thread_id"),
        "conversation_messages",
        ["thread_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_conversation_messages_thread_id"), table_name="conversation_messages")
    op.drop_index("ix_conversation_msg_thread_created", table_name="conversation_messages")
    op.drop_table("conversation_messages")
