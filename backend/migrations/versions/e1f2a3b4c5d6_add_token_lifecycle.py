"""Separate API and MCP credentials and expire legacy tokens.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("access_tokens")}
    if {"audience", "resource", "key_version", "expires_at"} <= columns:
        return  # Legacy adoption may already have created the current table.
    op.add_column(
        "access_tokens", sa.Column("audience", sa.String(8), server_default="api", nullable=False)
    )
    op.add_column("access_tokens", sa.Column("resource", sa.String(512), nullable=True))
    op.add_column(
        "access_tokens", sa.Column("key_version", sa.Integer(), server_default="1", nullable=False)
    )
    expires = sa.DateTime(timezone=True)
    op.add_column("access_tokens", sa.Column("expires_at", expires, nullable=True))
    tokens = sa.table("access_tokens", sa.column("expires_at", expires))
    op.execute(tokens.update().values(expires_at=datetime.now(UTC) + timedelta(days=7)))
    with op.batch_alter_table("access_tokens") as batch:
        batch.alter_column("expires_at", existing_type=expires, nullable=False)


def downgrade() -> None:
    raise RuntimeError("Restore a pre-upgrade backup instead of removing token security metadata")
