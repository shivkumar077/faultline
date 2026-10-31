import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.code_snapshot import CodeSnapshotResponse
from app.services.snapshot_service import snapshot_service

router = APIRouter(prefix="/snapshots", tags=["Snapshots"])


@router.get(
    "/{snapshot_id}",
    response_model=CodeSnapshotResponse,
)
def get_snapshot(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> CodeSnapshotResponse:
    """Retrieve code snapshot inventory and metadata by UUID."""
    return snapshot_service.get_snapshot(db, snapshot_id)
