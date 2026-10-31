import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analysis_run import AnalysisRunDetailResponse, AnalysisRunResponse
from app.schemas.common import PaginatedResponse
from app.schemas.mutation_record import MutationRecordResponse
from app.services.analysis_service import analysis_service
from app.services.mutation_service import mutation_service

router = APIRouter(prefix="/analyses", tags=["Analyses"])


@router.get("", response_model=PaginatedResponse[AnalysisRunResponse])
def list_analyses(
    project_id: uuid.UUID | None = Query(default=None, description="Filter analyses by project ID"),
    status: str | None = Query(default=None, description="Filter analyses by status"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AnalysisRunResponse]:
    """Retrieve a paginated list of analysis runs with optional project or status filters."""
    return analysis_service.list_analyses(
        db, project_id=project_id, status=status, page=page, page_size=page_size
    )


@router.get("/{analysis_id}", response_model=AnalysisRunDetailResponse)
def get_analysis(
    analysis_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> AnalysisRunDetailResponse:
    """Retrieve detailed analysis run metadata and execution counts by UUID."""
    return analysis_service.get_analysis(db, analysis_id)


@router.get("/{analysis_id}/mutations", response_model=PaginatedResponse[MutationRecordResponse])
def list_analysis_mutations(
    analysis_id: uuid.UUID,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[MutationRecordResponse]:
    """Retrieve a paginated list of mutation records generated for an analysis run."""
    return mutation_service.list_analysis_mutations(db, analysis_id, page=page, page_size=page_size)
