import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.failure_report import FailureReport
    from app.models.mutation_record import MutationRecord


class ExecutionResult(Base):
    __tablename__ = "execution_results"
    __table_args__ = (UniqueConstraint("mutation_record_id", name="uq_execution_result_mutation"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    mutation_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("mutation_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skipped_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mutation_application_status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )
    infrastructure_error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    test_output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    mutation_record: Mapped["MutationRecord"] = relationship(
        "MutationRecord", back_populates="execution_results"
    )
    failure_reports: Mapped[list["FailureReport"]] = relationship(
        "FailureReport", back_populates="execution_result"
    )

    def __repr__(self) -> str:
        return (
            f"<ExecutionResult(id={self.id}, status='{self.status}', exit_code={self.exit_code})>"
        )
