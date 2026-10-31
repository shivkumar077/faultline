import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateResourceException, NotFoundException
from app.core.validators import validate_and_normalize_github_url
from app.models.repository_connection import RepositoryConnection
from app.repositories.project_repository import project_repository
from app.repositories.repository_connection_repository import (
    repository_connection_repository,
)
from app.schemas.repository_connection import (
    RepositoryConnectionResponse,
    RepositoryRegistrationRequest,
)


class RepositoryService:
    def __init__(self):
        self.repo = repository_connection_repository
        self.project_repo = project_repository

    def register_repository(
        self,
        db: Session,
        project_id: uuid.UUID,
        req: RepositoryRegistrationRequest,
    ) -> RepositoryConnectionResponse:
        project = self.project_repo.get(db, project_id)
        if not project:
            raise NotFoundException(resource="Project", identifier=project_id)

        normalized_url = validate_and_normalize_github_url(req.repository_url)
        branch = req.branch.strip() or "main"

        existing = self.repo.get_by_project_and_url(db, project_id, normalized_url)
        if existing:
            raise DuplicateResourceException(
                resource="RepositoryConnection",
                field="repository_url",
                value=normalized_url,
            )

        data = {
            "project_id": project_id,
            "provider": "github",
            "repository_url": normalized_url,
            "branch": branch,
            "auth_type": "none",
            "status": "connected",
        }
        conn = self.repo.create(db, obj_in=data)
        return RepositoryConnectionResponse.model_validate(conn)

    def list_project_repositories(
        self, db: Session, project_id: uuid.UUID
    ) -> Sequence[RepositoryConnectionResponse]:
        project = self.project_repo.get(db, project_id)
        if not project:
            raise NotFoundException(resource="Project", identifier=project_id)

        connections = self.repo.get_by_project(db, project_id)
        return [RepositoryConnectionResponse.model_validate(c) for c in connections]

    def get_repository(self, db: Session, repository_id: uuid.UUID) -> RepositoryConnectionResponse:
        conn = self.repo.get(db, repository_id)
        if not conn:
            raise NotFoundException(resource="RepositoryConnection", identifier=repository_id)
        return RepositoryConnectionResponse.model_validate(conn)

    def get_repository_model(self, db: Session, repository_id: uuid.UUID) -> RepositoryConnection:
        conn = self.repo.get(db, repository_id)
        if not conn:
            raise NotFoundException(resource="RepositoryConnection", identifier=repository_id)
        return conn


repository_service = RepositoryService()
