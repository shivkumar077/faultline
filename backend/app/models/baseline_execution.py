import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun
    from app.models.code_snapshot import CodeSnapshot


class BaselineExecution(Base):
    __tablename__ = "baseline_executions"

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
    code_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    command: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    analysis_run: Mapped["AnalysisRun"] = relationship(
        "AnalysisRun", back_populates="baseline_executions"
    )
    code_snapshot: Mapped["CodeSnapshot"] = relationship(
        "CodeSnapshot", back_populates="baseline_executions"
    )

    def __repr__(self) -> str:
        return (
            f"<BaselineExecution(id={self.id}, status='{self.status}', command='{self.command}')>"
        )
