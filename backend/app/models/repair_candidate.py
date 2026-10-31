import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun
    from app.models.code_snapshot import CodeSnapshot
    from app.models.failure_report import FailureReport
    from app.models.mutation_record import MutationRecord
    from app.models.repair_evaluation import RepairEvaluation


class RepairCandidate(Base):
    __tablename__ = "repair_candidates"
    __table_args__ = (
        UniqueConstraint(
            "failure_report_id",
            "code_snapshot_id",
            "repair_strategy",
            name="uq_repair_candidate_diagnosis_snapshot_strategy",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    failure_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("failure_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mutation_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("mutation_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    snapshot_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    target_file: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_expression: Mapped[str] = mapped_column(Text, nullable=False)
    replacement_expression: Mapped[str] = mapped_column(Text, nullable=False)
    repair_strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    patch_content: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(50), nullable=False)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    failure_report: Mapped["FailureReport"] = relationship(
        "FailureReport", back_populates="repair_candidates"
    )
    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun", back_populates="repair_candidates"
    )
    code_snapshot: Mapped["CodeSnapshot"] = relationship(
        "CodeSnapshot", back_populates="repair_candidates"
    )
    mutation_record: Mapped["MutationRecord | None"] = relationship(
        "MutationRecord", back_populates="repair_candidates"
    )
    evaluations: Mapped[list["RepairEvaluation"]] = relationship(
        "RepairEvaluation", back_populates="repair_candidate", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<RepairCandidate(id={self.id}, strategy='{self.repair_strategy}', "
            f"review_status='{self.review_status}')>"
        )
