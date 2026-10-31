"""Initial schema creation for Faultline

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-31 20:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Projects
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_name", "projects", ["name"])
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)
    op.create_index("ix_projects_status", "projects", ["status"])

    # 2. Repository Connections
    op.create_table(
        "repository_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="github"),
        sa.Column("repository_url", sa.String(length=512), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False, server_default="main"),
        sa.Column("auth_type", sa.String(length=50), nullable=False, server_default="none"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="connected"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_repository_connections_project_id", "repository_connections", ["project_id"]
    )
    op.create_index("ix_repository_connections_status", "repository_connections", ["status"])

    # 3. Code Snapshots
    op.create_table(
        "code_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("repository_connection_id", sa.Uuid(), nullable=True),
        sa.Column("commit_hash", sa.String(length=64), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False, server_default="main"),
        sa.Column("file_tree_summary", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="captured"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["repository_connection_id"], ["repository_connections.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_snapshots_project_id", "code_snapshots", ["project_id"])
    op.create_index(
        "ix_code_snapshots_repository_connection_id", "code_snapshots", ["repository_connection_id"]
    )
    op.create_index("ix_code_snapshots_commit_hash", "code_snapshots", ["commit_hash"])
    op.create_index("ix_code_snapshots_status", "code_snapshots", ["status"])

    # 4. Analysis Runs
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("code_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["code_snapshot_id"], ["code_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_runs_project_id", "analysis_runs", ["project_id"])
    op.create_index("ix_analysis_runs_code_snapshot_id", "analysis_runs", ["code_snapshot_id"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])

    # 5. Baseline Executions
    op.create_table(
        "baseline_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("code_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("command", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["code_snapshot_id"], ["code_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_baseline_executions_analysis_run_id", "baseline_executions", ["analysis_run_id"]
    )
    op.create_index(
        "ix_baseline_executions_code_snapshot_id", "baseline_executions", ["code_snapshot_id"]
    )
    op.create_index("ix_baseline_executions_status", "baseline_executions", ["status"])

    # 6. Mutation Records
    op.create_table(
        "mutation_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("mutation_type", sa.String(length=100), nullable=False),
        sa.Column("target_file", sa.String(length=1024), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("original_code", sa.Text(), nullable=False),
        sa.Column("mutated_code", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="applied"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mutation_records_analysis_run_id", "mutation_records", ["analysis_run_id"])
    op.create_index("ix_mutation_records_mutation_type", "mutation_records", ["mutation_type"])
    op.create_index("ix_mutation_records_status", "mutation_records", ["status"])

    # 7. Execution Results
    op.create_table(
        "execution_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mutation_record_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("test_output", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["mutation_record_id"], ["mutation_records.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_execution_results_mutation_record_id", "execution_results", ["mutation_record_id"]
    )
    op.create_index("ix_execution_results_status", "execution_results", ["status"])

    # 8. Failure Reports
    op.create_table(
        "failure_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("execution_result_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("failure_type", sa.String(length=100), nullable=False),
        sa.Column("root_cause_analysis", sa.Text(), nullable=True),
        sa.Column("suggested_repair", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=50), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="open"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["execution_result_id"], ["execution_results.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_failure_reports_analysis_run_id", "failure_reports", ["analysis_run_id"])
    op.create_index(
        "ix_failure_reports_execution_result_id", "failure_reports", ["execution_result_id"]
    )
    op.create_index("ix_failure_reports_failure_type", "failure_reports", ["failure_type"])
    op.create_index("ix_failure_reports_severity", "failure_reports", ["severity"])
    op.create_index("ix_failure_reports_status", "failure_reports", ["status"])


def downgrade() -> None:
    op.drop_table("failure_reports")
    op.drop_table("execution_results")
    op.drop_table("mutation_records")
    op.drop_table("baseline_executions")
    op.drop_table("analysis_runs")
    op.drop_table("code_snapshots")
    op.drop_table("repository_connections")
    op.drop_table("projects")
