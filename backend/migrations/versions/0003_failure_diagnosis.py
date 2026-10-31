"""Extend failure reports with deterministic diagnosis evidence.

Revision ID: 0003_failure_diagnosis
Revises: 0002_execution_engine
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_failure_diagnosis"
down_revision: str | None = "0002_execution_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("failure_reports") as batch_op:
        batch_op.add_column(sa.Column("baseline_execution_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("mutation_record_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("diagnosis_key", sa.String(64), nullable=True))
        for column, column_type in (
            ("category", sa.String(50)),
            ("confidence_score", sa.Float()),
            ("causal_attribution", sa.String(50)),
            ("affected_test", sa.String(1024)),
            ("test_identifier", sa.String(1024)),
            ("test_file", sa.String(1024)),
            ("test_class", sa.String(255)),
            ("test_function", sa.String(255)),
            ("mutation_file", sa.String(1024)),
            ("mutation_line", sa.Integer()),
            ("original_expression", sa.Text()),
            ("mutated_expression", sa.Text()),
            ("exception_type", sa.String(512)),
            ("exception_message", sa.Text()),
            ("failing_assertion", sa.Text()),
            ("failure_summary", sa.Text()),
            ("source_file", sa.String(1024)),
            ("source_line", sa.Integer()),
            ("source_function", sa.String(255)),
            ("traceback_frames", sa.JSON()),
            ("evidence", sa.JSON()),
            ("comparison_summary", sa.Text()),
        ):
            batch_op.add_column(sa.Column(column, column_type, nullable=True))
        batch_op.create_foreign_key(
            "fk_failure_reports_baseline_execution_id",
            "baseline_executions",
            ["baseline_execution_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_failure_reports_mutation_record_id",
            "mutation_records",
            ["mutation_record_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_failure_reports_baseline_execution_id",
        "failure_reports",
        ["baseline_execution_id"],
    )
    op.create_index(
        "ix_failure_reports_mutation_record_id",
        "failure_reports",
        ["mutation_record_id"],
    )
    op.create_index("ix_failure_reports_category", "failure_reports", ["category"])
    op.create_index(
        "uq_failure_reports_diagnosis_key",
        "failure_reports",
        ["diagnosis_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_failure_reports_diagnosis_key", table_name="failure_reports")
    op.drop_index("ix_failure_reports_category", table_name="failure_reports")
    op.drop_index("ix_failure_reports_mutation_record_id", table_name="failure_reports")
    op.drop_index("ix_failure_reports_baseline_execution_id", table_name="failure_reports")
    with op.batch_alter_table("failure_reports") as batch_op:
        batch_op.drop_constraint("fk_failure_reports_mutation_record_id", type_="foreignkey")
        batch_op.drop_constraint("fk_failure_reports_baseline_execution_id", type_="foreignkey")
        for column in (
            "comparison_summary",
            "evidence",
            "traceback_frames",
            "source_function",
            "source_line",
            "source_file",
            "failure_summary",
            "failing_assertion",
            "exception_message",
            "exception_type",
            "mutated_expression",
            "original_expression",
            "mutation_line",
            "mutation_file",
            "test_function",
            "test_class",
            "test_file",
            "test_identifier",
            "affected_test",
            "causal_attribution",
            "confidence_score",
            "category",
            "diagnosis_key",
            "mutation_record_id",
            "baseline_execution_id",
        ):
            batch_op.drop_column(column)
