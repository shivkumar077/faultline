"""Persist baseline and mutant execution metadata.

Revision ID: 0002_execution_engine
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_execution_engine"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "baseline_executions",
        sa.Column("command_identifier", sa.String(50), server_default="pytest", nullable=False),
    )
    op.add_column(
        "baseline_executions",
        sa.Column("framework", sa.String(50), server_default="none", nullable=False),
    )
    op.add_column(
        "baseline_executions",
        sa.Column("test_files_count", sa.Integer(), server_default="0", nullable=False),
    )
    for column in ("passed_count", "failed_count", "skipped_count"):
        op.add_column("baseline_executions", sa.Column(column, sa.Integer(), nullable=True))
    op.add_column(
        "baseline_executions",
        sa.Column("timed_out", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "baseline_executions", sa.Column("infrastructure_error", sa.String(100), nullable=True)
    )
    op.create_index(
        "uq_baseline_analysis_run", "baseline_executions", ["analysis_run_id"], unique=True
    )

    op.add_column("mutation_records", sa.Column("col_offset", sa.Integer(), nullable=True))
    op.add_column("mutation_records", sa.Column("source_sha256", sa.String(64), nullable=True))

    for column in ("passed_count", "failed_count", "skipped_count"):
        op.add_column("execution_results", sa.Column(column, sa.Integer(), nullable=True))
    op.add_column(
        "execution_results",
        sa.Column("timed_out", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "execution_results",
        sa.Column(
            "mutation_application_status",
            sa.String(50),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "execution_results", sa.Column("infrastructure_error", sa.String(100), nullable=True)
    )
    op.create_index(
        "uq_execution_result_mutation", "execution_results", ["mutation_record_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_execution_result_mutation", table_name="execution_results")
    op.drop_column("execution_results", "infrastructure_error")
    op.drop_column("execution_results", "mutation_application_status")
    op.drop_column("execution_results", "timed_out")
    for column in ("skipped_count", "failed_count", "passed_count"):
        op.drop_column("execution_results", column)

    op.drop_column("mutation_records", "source_sha256")
    op.drop_column("mutation_records", "col_offset")

    op.drop_index("uq_baseline_analysis_run", table_name="baseline_executions")
    op.drop_column("baseline_executions", "infrastructure_error")
    op.drop_column("baseline_executions", "timed_out")
    for column in (
        "skipped_count",
        "failed_count",
        "passed_count",
        "test_files_count",
        "framework",
    ):
        op.drop_column("baseline_executions", column)
    op.drop_column("baseline_executions", "command_identifier")
