import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun
    from app.models.execution_result import ExecutionResult


class FailureReport(Base):
    __tablename__ = "failure_reports"

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
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    failure_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
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

    def __repr__(self) -> str:
        return f"<FailureReport(id={self.id}, title='{self.title}', severity='{self.severity}')>"
