"""Remember vector collections so privacy cleanup covers retired generations."""

import sqlalchemy as sa
from alembic import op

revision = "14c5d6e7f8a9"
down_revision = "03b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("index_generations"):
        op.create_table(
            "index_generations",
            sa.Column("collection", sa.String(255), primary_key=True),
            sa.Column("fingerprint", sa.String(64), nullable=False),
        )
    audit = sa.table(
        "audit_events", sa.column("id", sa.String()), sa.column("action", sa.String()),
        sa.column("details", sa.JSON()),
    )
    # Limit historical remediation to MCP search events. Keep the event, IDs,
    # and result count while dropping the old free-text search query.
    connection = op.get_bind()
    cursor = ""
    while True:
        rows = connection.execute(sa.select(audit.c.id, audit.c.details).where(
            audit.c.action == "mcp.evidence.search", audit.c.id > cursor,
        ).order_by(audit.c.id).limit(500)).all()
        if not rows:
            break
        for event_id, details in rows:
            count = details.get("count") if isinstance(details, dict) else None
            safe = {"count": count} if type(count) is int and count >= 0 else {}
            connection.execute(audit.update().where(audit.c.id == event_id).values(details=safe))
        cursor = rows[-1][0]


def downgrade() -> None:
    raise RuntimeError("Restore a backup instead of removing the vector cleanup registry")
