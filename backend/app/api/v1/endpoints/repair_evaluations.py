import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.repair_evaluation import (
    RepairEvaluationRequest,
    RepairEvaluationResponse,
)
from app.services.repair_evaluation_service import repair_evaluation_service

router = APIRouter(tags=["Repair evaluations"])


@router.post(
    "/repair-candidates/{candidate_id}/evaluations",
    response_model=RepairEvaluationResponse,
)
def evaluate_repair_candidate(
    candidate_id: uuid.UUID,
    request: RepairEvaluationRequest,
    db: Session = Depends(get_db),
) -> RepairEvaluationResponse:
    """Apply a candidate patch in isolation and run tests through Docker."""
    return repair_evaluation_service.evaluate_candidate(db, candidate_id, request)


@router.get(
    "/repair-candidates/{candidate_id}/evaluations",
    response_model=PaginatedResponse[RepairEvaluationResponse],
)
def list_candidate_evaluations(
    candidate_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[RepairEvaluationResponse]:
    """List a candidate's persisted evaluation history."""
    return repair_evaluation_service.list_for_candidate(
        db,
        candidate_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/repair-evaluations/{evaluation_id}",
    response_model=RepairEvaluationResponse,
)
def get_repair_evaluation(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RepairEvaluationResponse:
    """Retrieve a persisted repair evaluation."""
    return repair_evaluation_service.get_evaluation(db, evaluation_id)
