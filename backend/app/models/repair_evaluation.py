import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun
    from app.models.failure_report import FailureReport
    from app.models.repair_candidate import RepairCandidate


class RepairEvaluation(Base):
    __tablename__ = "repair_evaluations"
    __table_args__ = (
        Index(
            "uq_repair_evaluations_active_candidate",
            "repair_candidate_id",
            unique=True,
            sqlite_where=text("status = 'RUNNING'"),
            postgresql_where=text("status = 'RUNNING'"),
        ),
        Index("ix_repair_evaluations_candidate_created", "repair_candidate_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    repair_candidate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repair_candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    failure_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("failure_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    baseline_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("baseline_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    mutant_execution_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution_results.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skipped_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    forgefit_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_requested"
    )
    forgefit_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    forgefit_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    forgefit_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repair_candidate: Mapped["RepairCandidate"] = relationship(
        "RepairCandidate", back_populates="evaluations"
    )
    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun", back_populates="repair_evaluations"
    )
    failure_report: Mapped["FailureReport"] = relationship(
        "FailureReport", back_populates="repair_evaluations"
    )
