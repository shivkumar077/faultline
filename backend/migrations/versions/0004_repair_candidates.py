"""Persist generated repair candidates and review state.

Revision ID: 0004_repair_candidates
Revises: 0003_failure_diagnosis
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_repair_candidates"
down_revision: str | None = "0003_failure_diagnosis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repair_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("failure_report_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("code_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("mutation_record_id", sa.Uuid(), nullable=True),
        sa.Column("snapshot_commit", sa.String(length=64), nullable=False),
        sa.Column("target_file", sa.String(length=1024), nullable=False),
        sa.Column("original_source_sha256", sa.String(length=64), nullable=False),
        sa.Column("proposed_source_sha256", sa.String(length=64), nullable=False),
        sa.Column("original_expression", sa.Text(), nullable=False),
        sa.Column("replacement_expression", sa.Text(), nullable=False),
        sa.Column("repair_strategy", sa.String(length=64), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("patch_content", sa.Text(), nullable=False),
        sa.Column("validation_status", sa.String(length=50), nullable=False),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["analysis_runs.id"],
            name="fk_repair_candidates_analysis_run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["code_snapshot_id"],
            ["code_snapshots.id"],
            name="fk_repair_candidates_code_snapshot_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["failure_report_id"],
            ["failure_reports.id"],
            name="fk_repair_candidates_failure_report_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mutation_record_id"],
            ["mutation_records.id"],
            name="fk_repair_candidates_mutation_record_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "failure_report_id",
            "code_snapshot_id",
            "repair_strategy",
            name="uq_repair_candidate_diagnosis_snapshot_strategy",
        ),
    )
    op.create_index(
        "ix_repair_candidates_analysis_run_id",
        "repair_candidates",
        ["analysis_run_id"],
    )
    op.create_index(
        "ix_repair_candidates_code_snapshot_id",
        "repair_candidates",
        ["code_snapshot_id"],
    )
    op.create_index(
        "ix_repair_candidates_failure_report_id",
        "repair_candidates",
        ["failure_report_id"],
    )
    op.create_index(
        "ix_repair_candidates_mutation_record_id",
        "repair_candidates",
        ["mutation_record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_repair_candidates_mutation_record_id", table_name="repair_candidates")
    op.drop_index("ix_repair_candidates_failure_report_id", table_name="repair_candidates")
    op.drop_index("ix_repair_candidates_code_snapshot_id", table_name="repair_candidates")
    op.drop_index("ix_repair_candidates_analysis_run_id", table_name="repair_candidates")
    op.drop_table("repair_candidates")
