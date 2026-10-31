import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun
    from app.models.baseline_execution import BaselineExecution
    from app.models.execution_result import ExecutionResult
    from app.models.mutation_record import MutationRecord
    from app.models.repair_candidate import RepairCandidate


class FailureReport(Base):
    __tablename__ = "failure_reports"
    __table_args__ = (Index("uq_failure_reports_diagnosis_key", "diagnosis_key", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    execution_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("execution_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    baseline_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("baseline_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mutation_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("mutation_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    diagnosis_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    failure_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    causal_attribution: Mapped[str | None] = mapped_column(String(50), nullable=True)
    affected_test: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    test_identifier: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    test_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    test_class: Mapped[str | None] = mapped_column(String(255), nullable=True)
    test_function: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mutation_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    mutation_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    mutated_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(512), nullable=True)
    exception_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failing_assertion: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_function: Mapped[str | None] = mapped_column(String(255), nullable=True)
    traceback_frames: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    comparison_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_repair: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(50), default="medium", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun", back_populates="failure_reports"
    )
    execution_result: Mapped[Optional["ExecutionResult"]] = relationship(
        "ExecutionResult", back_populates="failure_reports"
    )
    baseline_execution: Mapped[Optional["BaselineExecution"]] = relationship(
        "BaselineExecution", back_populates="failure_reports"
    )
    mutation_record: Mapped[Optional["MutationRecord"]] = relationship(
        "MutationRecord", back_populates="failure_reports"
    )
    repair_candidates: Mapped[list["RepairCandidate"]] = relationship(
        "RepairCandidate", back_populates="failure_report", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<FailureReport(id={self.id}, title='{self.title}', severity='{self.severity}')>"
