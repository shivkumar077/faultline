import math
import uuid
from typing import Optional
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateResourceException, NotFoundException
from app.models.project import Project
from app.repositories.project_repository import project_repository
from app.schemas.common import PaginatedResponse
from app.schemas.project import (
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectUpdate,
    slugify,
)


class ProjectService:
    def __init__(self):
        self.repo = project_repository

    def create_project(self, db: Session, project_in: ProjectCreate) -> ProjectResponse:
        slug = project_in.slug or slugify(project_in.name)
        existing = self.repo.get_by_slug(db, slug)
        if existing:
            raise DuplicateResourceException(
                resource="Project", field="slug", value=slug
            )

        data = project_in.model_dump()
        data["slug"] = slug
        project = self.repo.create(db, obj_in=data)
        return ProjectResponse.model_validate(project)

    def get_project(self, db: Session, project_id: uuid.UUID) -> ProjectDetailResponse:
        result = self.repo.get_with_counts(db, project_id)
        if not result:
            raise NotFoundException(resource="Project", identifier=project_id)

        project, repo_count, snapshot_count, analysis_count = result
        response = ProjectDetailResponse.model_validate(project)
        response.repository_connections_count = repo_count
        response.code_snapshots_count = snapshot_count
        response.analysis_runs_count = analysis_count
        return response

    def list_projects(
        self, db: Session, *, page: int = 1, page_size: int = 20
    ) -> PaginatedResponse[ProjectResponse]:
        skip = (page - 1) * page_size
        items, total = self.repo.get_multi(db, skip=skip, limit=page_size)
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return PaginatedResponse[ProjectResponse](
            items=[ProjectResponse.model_validate(p) for p in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def update_project(
        self, db: Session, project_id: uuid.UUID, project_in: ProjectUpdate
    ) -> ProjectResponse:
        project = self.repo.get(db, project_id)
        if not project:
            raise NotFoundException(resource="Project", identifier=project_id)

        if project_in.slug and project_in.slug != project.slug:
            existing = self.repo.get_by_slug(db, project_in.slug)
            if existing and existing.id != project_id:
                raise DuplicateResourceException(
                    resource="Project", field="slug", value=project_in.slug
                )

        updated = self.repo.update(db, db_obj=project, obj_in=project_in)
        return ProjectResponse.model_validate(updated)

    def delete_project(self, db: Session, project_id: uuid.UUID) -> ProjectResponse:
        project = self.repo.get(db, project_id)
        if not project:
            raise NotFoundException(resource="Project", identifier=project_id)

        self.repo.delete(db, id=project_id)
        return ProjectResponse.model_validate(project)


project_service = ProjectService()
