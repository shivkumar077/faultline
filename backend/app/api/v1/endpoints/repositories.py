import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.code_snapshot import CodeSnapshotResponse
from app.schemas.repository_connection import (
    RepositoryConnectionResponse,
    RepositoryRegistrationRequest,
)
from app.services.repository_service import repository_service
from app.services.snapshot_service import snapshot_service

router = APIRouter(tags=["Repositories"])


@router.post(
    "/projects/{project_id}/repositories",
    response_model=RepositoryConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_project_repository(
    project_id: uuid.UUID,
    payload: RepositoryRegistrationRequest,
    db: Session = Depends(get_db),
) -> RepositoryConnectionResponse:
    """Register a public GitHub repository for a specified project."""
    return repository_service.register_repository(db, project_id, payload)


@router.get(
    "/projects/{project_id}/repositories",
    response_model=Sequence[RepositoryConnectionResponse],
)
def list_project_repositories(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Sequence[RepositoryConnectionResponse]:
    """Retrieve all repository connections configured for a project."""
    return repository_service.list_project_repositories(db, project_id)


@router.get(
    "/repositories/{repository_id}",
    response_model=RepositoryConnectionResponse,
)
def get_repository(
    repository_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RepositoryConnectionResponse:
    """Retrieve repository connection details by UUID."""
    return repository_service.get_repository(db, repository_id)


@router.post(
    "/repositories/{repository_id}/sync",
    response_model=CodeSnapshotResponse,
    status_code=status.HTTP_200_OK,
)
def sync_repository(
    repository_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> CodeSnapshotResponse:
    """Trigger ingestion and snapshot generation for the specified repository connection."""
    return snapshot_service.sync_repository(db, repository_id)


@router.get(
    "/repositories/{repository_id}/snapshots",
    response_model=Sequence[CodeSnapshotResponse],
)
def list_repository_snapshots(
    repository_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Sequence[CodeSnapshotResponse]:
    """List all captured source snapshots for a repository connection."""
    return snapshot_service.list_repository_snapshots(db, repository_id)
