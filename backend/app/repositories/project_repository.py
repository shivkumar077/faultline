import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.code_snapshot import CodeSnapshot
from app.models.project import Project
from app.models.repository_connection import RepositoryConnection
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self):
        super().__init__(Project)

    def get_by_slug(self, db: Session, slug: str) -> Project | None:
        stmt = select(Project).where(Project.slug == slug)
        return db.scalars(stmt).first()

    def get_with_counts(self, db: Session, id: uuid.UUID) -> tuple[Project, int, int, int] | None:
        project = self.get(db, id)
        if not project:
            return None

        repo_count = (
            db.scalar(
                select(func.count())
                .select_from(RepositoryConnection)
                .where(RepositoryConnection.project_id == id)
            )
            or 0
        )
        snapshot_count = (
            db.scalar(
                select(func.count()).select_from(CodeSnapshot).where(CodeSnapshot.project_id == id)
            )
            or 0
        )
        analysis_count = (
            db.scalar(
                select(func.count()).select_from(AnalysisRun).where(AnalysisRun.project_id == id)
            )
            or 0
        )

        return project, repo_count, snapshot_count, analysis_count


project_repository = ProjectRepository()
