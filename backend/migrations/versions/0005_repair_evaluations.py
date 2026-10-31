"""Persist isolated repair candidate evaluation results.

Revision ID: 0005_repair_evaluations
Revises: 0004_repair_candidates
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_repair_evaluations"
down_revision: str | None = "0004_repair_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repair_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repair_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("failure_report_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_execution_id", sa.Uuid(), nullable=True),
        sa.Column("mutant_execution_result_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("passed_count", sa.Integer(), nullable=True),
        sa.Column("failed_count", sa.Integer(), nullable=True),
        sa.Column("skipped_count", sa.Integer(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "forgefit_status",
            sa.String(length=32),
            server_default="not_requested",
            nullable=False,
        ),
        sa.Column("forgefit_run_id", sa.String(length=128), nullable=True),
        sa.Column("forgefit_result", sa.JSON(), nullable=True),
        sa.Column("forgefit_error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["analysis_runs.id"],
            name="fk_repair_evaluations_analysis_run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["baseline_execution_id"],
            ["baseline_executions.id"],
            name="fk_repair_evaluations_baseline_execution_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["failure_report_id"],
            ["failure_reports.id"],
            name="fk_repair_evaluations_failure_report_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mutant_execution_result_id"],
            ["execution_results.id"],
            name="fk_repair_evaluations_mutant_execution_result_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["repair_candidate_id"],
            ["repair_candidates.id"],
            name="fk_repair_evaluations_repair_candidate_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_repair_evaluations_repair_candidate_id",
        "repair_evaluations",
        ["repair_candidate_id"],
    )
    op.create_index(
        "ix_repair_evaluations_analysis_run_id",
        "repair_evaluations",
        ["analysis_run_id"],
    )
    op.create_index(
        "ix_repair_evaluations_failure_report_id",
        "repair_evaluations",
        ["failure_report_id"],
    )
    op.create_index(
        "ix_repair_evaluations_status",
        "repair_evaluations",
        ["status"],
    )
    op.create_index(
        "ix_repair_evaluations_candidate_created",
        "repair_evaluations",
        ["repair_candidate_id", "created_at"],
    )
    op.create_index(
        "uq_repair_evaluations_active_candidate",
        "repair_evaluations",
        ["repair_candidate_id"],
        unique=True,
        sqlite_where=sa.text("status = 'RUNNING'"),
        postgresql_where=sa.text("status = 'RUNNING'"),
    )


def downgrade() -> None:
    op.drop_index("uq_repair_evaluations_active_candidate", table_name="repair_evaluations")
    op.drop_index("ix_repair_evaluations_candidate_created", table_name="repair_evaluations")
    op.drop_index("ix_repair_evaluations_status", table_name="repair_evaluations")
    op.drop_index("ix_repair_evaluations_failure_report_id", table_name="repair_evaluations")
    op.drop_index("ix_repair_evaluations_analysis_run_id", table_name="repair_evaluations")
    op.drop_index("ix_repair_evaluations_repair_candidate_id", table_name="repair_evaluations")
    op.drop_table("repair_evaluations")
