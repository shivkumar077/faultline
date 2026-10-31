import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis_run import AnalysisRun
    from app.models.baseline_execution import BaselineExecution
    from app.models.project import Project
    from app.models.repository_connection import RepositoryConnection


class CodeSnapshot(Base):
    __tablename__ = "code_snapshots"

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
    repository_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repository_connections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    commit_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    file_tree_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="captured", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="code_snapshots")
    repository_connection: Mapped[Optional["RepositoryConnection"]] = relationship(
        "RepositoryConnection", back_populates="code_snapshots"
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        "AnalysisRun", back_populates="code_snapshot"
    )
    baseline_executions: Mapped[list["BaselineExecution"]] = relationship(
        "BaselineExecution", back_populates="code_snapshot"
    )

    def __repr__(self) -> str:
        return (
            f"<CodeSnapshot(id={self.id}, commit='{self.commit_hash[:7]}', branch='{self.branch}')>"
        )
