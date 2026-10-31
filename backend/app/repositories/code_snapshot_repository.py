import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.code_snapshot import CodeSnapshot
from app.repositories.base import BaseRepository


class CodeSnapshotRepository(BaseRepository[CodeSnapshot]):
    def __init__(self):
        super().__init__(CodeSnapshot)

    def get_by_project_and_commit(
        self, db: Session, project_id: uuid.UUID, commit_hash: str
    ) -> CodeSnapshot | None:
        stmt = select(CodeSnapshot).where(
            CodeSnapshot.project_id == project_id,
            CodeSnapshot.commit_hash == commit_hash,
        )
        return db.scalars(stmt).first()

    def get_by_repository(
        self, db: Session, repository_connection_id: uuid.UUID
    ) -> Sequence[CodeSnapshot]:
        stmt = (
            select(CodeSnapshot)
            .where(CodeSnapshot.repository_connection_id == repository_connection_id)
            .order_by(CodeSnapshot.created_at.desc())
        )
        return db.scalars(stmt).all()


code_snapshot_repository = CodeSnapshotRepository()
