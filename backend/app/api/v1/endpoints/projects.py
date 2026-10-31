import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.project import (
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
)
from app.services.project_service import project_service

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=PaginatedResponse[ProjectResponse])
def list_projects(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ProjectResponse]:
    """Retrieve a paginated list of registered projects."""
    return project_service.list_projects(db, page=page, page_size=page_size)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Create a new project."""
    return project_service.create_project(db, project_in)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProjectDetailResponse:
    """Retrieve a project by its unique UUID identifier with relationship counts."""
    return project_service.get_project(db, project_id)


@router.delete("/{project_id}", response_model=ProjectResponse)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Delete a project and its associated cascade data."""
    return project_service.delete_project(db, project_id)
