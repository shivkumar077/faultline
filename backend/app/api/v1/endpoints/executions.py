import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.execution import (
    ExecuteAnalysisRequest,
    ExecuteAnalysisResponse,
    ExecutionRecordResponse,
)
from app.services.execution_service import execution_service

router = APIRouter(tags=["Executions"])


@router.post(
    "/analyses/{analysis_id}/execute",
    response_model=ExecuteAnalysisResponse,
)
def execute_analysis(
    analysis_id: uuid.UUID,
    request: ExecuteAnalysisRequest,
    db: Session = Depends(get_db),
) -> ExecuteAnalysisResponse:
    """Run baseline tests, then execute each manifest mutant in an isolated container."""
    return execution_service.execute_analysis(
        db, analysis_id, timeout_seconds=request.timeout_seconds
    )


@router.get(
    "/analyses/{analysis_id}/executions",
    response_model=PaginatedResponse[ExecutionRecordResponse],
)
def list_analysis_executions(
    analysis_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ExecutionRecordResponse]:
    """List baseline and mutant execution records for an analysis."""
    return execution_service.list_executions(db, analysis_id, page=page, page_size=page_size)


@router.get("/executions/{execution_id}", response_model=ExecutionRecordResponse)
def get_execution(
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ExecutionRecordResponse:
    """Get one baseline or mutant execution by UUID."""
    return execution_service.get_execution(db, execution_id)
