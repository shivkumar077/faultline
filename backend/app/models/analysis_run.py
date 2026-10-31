import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.baseline_execution import BaselineExecution
    from app.models.code_snapshot import CodeSnapshot
    from app.models.failure_report import FailureReport
    from app.models.mutation_record import MutationRecord
    from app.models.project import Project


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False, index=True
    )
    summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    project: Mapped["Project"] = relationship("Project", back_populates="analysis_runs")
    code_snapshot: Mapped["CodeSnapshot"] = relationship(
        "CodeSnapshot", back_populates="analysis_runs"
    )
    baseline_executions: Mapped[List["BaselineExecution"]] = relationship(
        "BaselineExecution",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )
    mutation_records: Mapped[List["MutationRecord"]] = relationship(
        "MutationRecord",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )
    failure_reports: Mapped[List["FailureReport"]] = relationship(
        "FailureReport",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AnalysisRun(id={self.id}, status='{self.status}', project_id={self.project_id})>"
