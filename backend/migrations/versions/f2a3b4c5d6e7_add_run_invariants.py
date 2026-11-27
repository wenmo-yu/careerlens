"""Fence abandoned running rows and enforce one active execution per account."""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def _repair_running_rows(connection) -> None:
    metadata = sa.MetaData()
    runs = sa.Table("agent_runs", metadata, autoload_with=connection)
    steps = sa.Table("run_steps", metadata, autoload_with=connection)
    events = sa.Table("run_events", metadata, autoload_with=connection)
    running = connection.execute(
        sa.select(
            runs.c.id, runs.c.user_id, runs.c.lease_owner, runs.c.lease_until,
            runs.c.attempts, runs.c.max_attempts, runs.c.fencing_token, runs.c.event_seq,
        ).where(runs.c.status == "running").order_by(
            runs.c.user_id, runs.c.created_at, runs.c.id,
        )
    ).mappings().all()
    active_users = set()
    now = datetime.now(UTC)
    for row in running:
        valid = row["lease_owner"] and (row["lease_until"] or 0) > int(now.timestamp())
        if valid and row["user_id"] not in active_users:
            active_users.add(row["user_id"])
            continue
        failed = row["attempts"] >= row["max_attempts"]
        status = "failed" if failed else "interrupted"
        reason = "retries_exhausted" if failed else "lease_repaired"
        fence = row["fencing_token"] + 1
        seq = row["event_seq"] + 1
        fields = {
            "status": status, "lease_owner": None, "lease_until": None,
            "fencing_token": fence, "event_seq": seq, "error_code": reason if failed else None,
        }
        if failed:
            fields.update(payload={}, upload_bytes=None)
        connection.execute(runs.update().where(runs.c.id == row["id"]).values(**fields))
        connection.execute(steps.update().where(
            steps.c.run_id == row["id"], steps.c.status == "running",
        ).values(status=status, updated_at=now))
        connection.execute(events.insert().values(
            run_id=row["id"], seq=seq, user_id=row["user_id"], generation=fence,
            event_type=f"run.{status}", data={"reason": reason},
        ))


def upgrade() -> None:
    connection = op.get_bind()
    _repair_running_rows(connection)
    inspector = sa.inspect(connection)
    if "ck_running_has_lease" not in {
        row["name"] for row in inspector.get_check_constraints("agent_runs")
    }:
        with op.batch_alter_table("agent_runs") as batch:
            batch.create_check_constraint(
                "ck_running_has_lease",
                "status <> 'running' OR (lease_owner IS NOT NULL AND lease_until IS NOT NULL)",
            )
    if "uq_running_run_user" not in {row["name"] for row in inspector.get_indexes("agent_runs")}:
        running = sa.text("status = 'running'")
        op.create_index(
            "uq_running_run_user", "agent_runs", ["user_id"], unique=True,
            sqlite_where=running, postgresql_where=running,
        )
    for name, table, columns in (
        ("ix_saved_job_user_created", "saved_jobs", ["user_id", "created_at"]),
        ("ix_learning_progress_user_plan", "learning_progress", ["user_id", "plan_id"]),
    ):
        if name not in {row["name"] for row in inspector.get_indexes(table)}:
            op.create_index(name, table, columns)


def downgrade() -> None:
    op.drop_index("ix_learning_progress_user_plan", table_name="learning_progress")
    op.drop_index("ix_saved_job_user_created", table_name="saved_jobs")
    op.drop_index("uq_running_run_user", table_name="agent_runs")
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_constraint("ck_running_has_lease", type_="check")
