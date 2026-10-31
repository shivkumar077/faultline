import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun
    from app.models.execution_result import ExecutionResult


class MutationRecord(Base):
    __tablename__ = "mutation_records"

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
    mutation_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    target_file: Mapped[str] = mapped_column(String(1024), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_code: Mapped[str] = mapped_column(Text, nullable=False)
    mutated_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="applied", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun", back_populates="mutation_records"
    )
    execution_results: Mapped[List["ExecutionResult"]] = relationship(
        "ExecutionResult",
        back_populates="mutation_record",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<MutationRecord(id={self.id}, type='{self.mutation_type}', file='{self.target_file}:{self.line_number}')>"
