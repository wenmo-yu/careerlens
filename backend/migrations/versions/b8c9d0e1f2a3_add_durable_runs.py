"""Add the leased run queue, progress journal, and evidence index outbox."""

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("actor_token_id", sa.String(36)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("upload_bytes", sa.LargeBinary()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("confirmation", sa.String(16), nullable=False),
        sa.Column("fencing_token", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(36)),
        sa.Column("lease_until", sa.BigInteger()),
        sa.Column("input_epoch", sa.Integer(), nullable=False),
        sa.Column("target_key", sa.String(300)),
        sa.Column("target_generation", sa.Integer()),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("error_code", sa.String(40)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "request_key", name="uq_run_user_request_key"),
        sa.CheckConstraint(
            "status IN ('queued','running','waiting_confirmation','succeeded',"
            "'failed','cancelled','interrupted')",
            name="ck_run_status",
        ),
    )
    op.create_index("ix_run_queue", "agent_runs", ["status", "created_at", "id"])
    op.create_index("ix_run_leases", "agent_runs", ["status", "lease_until"])
    op.create_index("ix_run_user_queue", "agent_runs", ["user_id", "created_at", "id"])
    op.create_table(
        "run_scopes",
        sa.Column("user_id", sa.String(128), primary_key=True),
        sa.Column("key", sa.String(300), primary_key=True),
        sa.Column("generation", sa.Integer(), nullable=False),
    )
    op.create_index("ix_run_scope_user", "run_scopes", ["user_id"])
    op.create_table(
        "run_steps",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_run_steps_user_id", "run_steps", ["user_id"])
    op.create_table(
        "run_events",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_run_events_user_id", "run_events", ["user_id"])
    op.create_table(
        "evidence_index_work",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("ready_at", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_evidence_index_work_user_id", "evidence_index_work", ["user_id"])
    op.create_index("ix_evidence_index_work_ready_at", "evidence_index_work", ["ready_at"])


def downgrade() -> None:
    for table in ("evidence_index_work", "run_events", "run_steps", "run_scopes", "agent_runs"):
        op.drop_table(table)
