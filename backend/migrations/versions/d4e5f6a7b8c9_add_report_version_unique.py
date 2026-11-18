"""add unique (user_id, version) to career reports

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-18

Phase 1 consistency: report versions were allocated with max(version)+1, which
races under concurrent generation. A unique constraint makes collisions a
detectable IntegrityError that the service retries. Old databases may already
contain duplicate versions, so they are renumbered deterministically first.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deterministically renumber any pre-existing duplicate (user_id, version)
    # rows before adding the constraint. Keep the lowest id per (user, version)
    # at its version; push the rest above the current max for that user.
    conn = op.get_bind()
    users = conn.execute(sa.text("SELECT DISTINCT user_id FROM career_reports")).fetchall()
    for (user_id,) in users:
        max_version = conn.execute(
            sa.text("SELECT COALESCE(MAX(version), 0) FROM career_reports WHERE user_id = :u"),
            {"u": user_id},
        ).scalar_one()
        next_version = int(max_version) + 1
        rows = conn.execute(
            sa.text(
                "SELECT id FROM career_reports WHERE user_id = :u "
                "ORDER BY version, id"
            ),
            {"u": user_id},
        ).fetchall()
        seen: set[int] = set()
        for (row_id,) in rows:
            version_row = conn.execute(
                sa.text("SELECT version FROM career_reports WHERE id = :i"), {"i": row_id}
            ).scalar_one()
            version = int(version_row)
            if version in seen:
                conn.execute(
                    sa.text("UPDATE career_reports SET version = :v WHERE id = :i"),
                    {"v": next_version, "i": row_id},
                )
                next_version += 1
            else:
                seen.add(version)

    # batch_alter_table rebuilds the table on SQLite (which cannot ALTER ADD
    # CONSTRAINT) while issuing a plain ALTER on PostgreSQL.
    with op.batch_alter_table("career_reports") as batch:
        batch.create_unique_constraint(
            "uq_report_user_version", ["user_id", "version"]
        )


def downgrade() -> None:
    with op.batch_alter_table("career_reports") as batch:
        batch.drop_constraint("uq_report_user_version", type_="unique")
