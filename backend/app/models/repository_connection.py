import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.code_snapshot import CodeSnapshot
    from app.models.project import Project


class RepositoryConnection(Base):
    __tablename__ = "repository_connections"

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
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="github")
    repository_url: Mapped[str] = mapped_column(String(512), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    auth_type: Mapped[str] = mapped_column(String(50), default="none", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="connected", nullable=False, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    project: Mapped["Project"] = relationship("Project", back_populates="repository_connections")
    code_snapshots: Mapped[list["CodeSnapshot"]] = relationship(
        "CodeSnapshot", back_populates="repository_connection"
    )

    def __repr__(self) -> str:
        return (
            f"<RepositoryConnection(id={self.id}, provider='{self.provider}', "
            f"url='{self.repository_url}')>"
        )
