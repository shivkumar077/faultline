import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analysis_run import AnalysisRunDetailResponse
from app.schemas.code_snapshot import CodeSnapshotResponse
from app.schemas.mutation_record import GenerateMutationsRequest
from app.services.mutation_service import mutation_service
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


@router.post(
    "/{snapshot_id}/mutations",
    response_model=AnalysisRunDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_snapshot_mutations(
    snapshot_id: uuid.UUID,
    payload: GenerateMutationsRequest = GenerateMutationsRequest(),
    db: Session = Depends(get_db),
) -> AnalysisRunDetailResponse:
    """Generate deterministic AST-based code mutations for the target snapshot."""
    return mutation_service.generate_mutations(db, snapshot_id, payload)
