import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.repository_connection import RepositoryConnection
from app.repositories.base import BaseRepository


class RepositoryConnectionRepository(BaseRepository[RepositoryConnection]):
    def __init__(self):
        super().__init__(RepositoryConnection)

    def get_by_project_and_url(
        self, db: Session, project_id: uuid.UUID, repository_url: str
    ) -> RepositoryConnection | None:
        stmt = select(RepositoryConnection).where(
            RepositoryConnection.project_id == project_id,
            RepositoryConnection.repository_url == repository_url,
        )
        return db.scalars(stmt).first()

    def get_by_project(
        self, db: Session, project_id: uuid.UUID
    ) -> Sequence[RepositoryConnection]:
        stmt = (
            select(RepositoryConnection)
            .where(RepositoryConnection.project_id == project_id)
            .order_by(RepositoryConnection.created_at.desc())
        )
        return db.scalars(stmt).all()


repository_connection_repository = RepositoryConnectionRepository()
