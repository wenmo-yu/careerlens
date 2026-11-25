"""add HY4 assessment, constraints and profile dimensions

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-11-25

All four tables are user-owned self-reported data. They are kept separate
from profile_items so an assessment can never be promoted to a capability
fact. They must be included in privacy export and account deletion.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assessment_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("instrument", sa.String(length=50), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False, server_default="v1"),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("answers_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="self_report"),
        sa.Column("consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "taken_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "instrument", "version", "taken_at",
            name="uq_assessment_result_user_instrument_version_time",
        ),
    )
    op.create_index(op.f("ix_assessment_results_user_id"), "assessment_results", ["user_id"], unique=False)
    op.create_index(op.f("ix_assessment_results_created_at"), "assessment_results", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_assessment_result_user_instrument"),
        "assessment_results", ["user_id", "instrument"], unique=False,
    )

    op.create_table(
        "user_constraints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("strength", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="self_report"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", name="uq_user_constraint_user_kind"),
    )
    op.create_index(op.f("ix_user_constraints_user_id"), "user_constraints", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_constraints_created_at"), "user_constraints", ["created_at"], unique=False)

    op.create_table(
        "dimension_definitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="self_report"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_dimension_user_key"),
    )
    op.create_index(op.f("ix_dimension_definitions_user_id"), "dimension_definitions", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_dimension_user_enabled"),
        "dimension_definitions", ["user_id", "enabled"], unique=False,
    )

    op.create_table(
        "profile_extensions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("dimension_key", sa.String(length=80), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="self_report"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dimension_key", name="uq_profile_extension_user_dimension"),
    )
    op.create_index(op.f("ix_profile_extensions_user_id"), "profile_extensions", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_profile_extension_user_dimension"),
        "profile_extensions", ["user_id", "dimension_key"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_profile_extension_user_dimension"), table_name="profile_extensions")
    op.drop_index(op.f("ix_profile_extensions_user_id"), table_name="profile_extensions")
    op.drop_table("profile_extensions")
    op.drop_index(op.f("ix_dimension_user_enabled"), table_name="dimension_definitions")
    op.drop_index(op.f("ix_dimension_definitions_user_id"), table_name="dimension_definitions")
    op.drop_table("dimension_definitions")
    op.drop_index(op.f("ix_user_constraints_created_at"), table_name="user_constraints")
    op.drop_index(op.f("ix_user_constraints_user_id"), table_name="user_constraints")
    op.drop_table("user_constraints")
    op.drop_index(op.f("ix_assessment_result_user_instrument"), table_name="assessment_results")
    op.drop_index(op.f("ix_assessment_results_created_at"), table_name="assessment_results")
    op.drop_index(op.f("ix_assessment_results_user_id"), table_name="assessment_results")
    op.drop_table("assessment_results")
