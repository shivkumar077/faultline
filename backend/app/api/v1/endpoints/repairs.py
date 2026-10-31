import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.repair_candidate import (
    GenerateRepairCandidatesRequest,
    RepairCandidateResponse,
    RepairCandidateReviewRequest,
    RepairGenerationResponse,
    RepairPatchResponse,
)
from app.services.repair_service import repair_service

router = APIRouter(tags=["Repair candidates"])


@router.post(
    "/analyses/{analysis_id}/repair-candidates",
    response_model=RepairGenerationResponse,
)
def generate_analysis_repairs(
    analysis_id: uuid.UUID,
    request: GenerateRepairCandidatesRequest,
    db: Session = Depends(get_db),
) -> RepairGenerationResponse:
    """Generate patches for eligible persisted diagnoses in an analysis."""
    return repair_service.generate_for_analysis(
        db,
        analysis_id,
        failure_report_ids=request.failure_report_ids,
    )


@router.post(
    "/analyses/{analysis_id}/diagnoses/{failure_report_id}/repair-candidates",
    response_model=RepairGenerationResponse,
)
def generate_diagnosis_repairs(
    analysis_id: uuid.UUID,
    failure_report_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RepairGenerationResponse:
    """Generate a patch for one persisted diagnosis."""
    return repair_service.generate_for_diagnosis(db, analysis_id, failure_report_id)


@router.get(
    "/analyses/{analysis_id}/repair-candidates",
    response_model=PaginatedResponse[RepairCandidateResponse],
)
def list_analysis_repairs(
    analysis_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[RepairCandidateResponse]:
    """List repair candidates for one analysis."""
    return repair_service.list_for_analysis(db, analysis_id, page=page, page_size=page_size)


@router.get("/repair-candidates/{candidate_id}", response_model=RepairCandidateResponse)
def get_repair_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RepairCandidateResponse:
    """Retrieve repair metadata without the patch body."""
    return repair_service.get_candidate(db, candidate_id)


@router.get("/repair-candidates/{candidate_id}/diff", response_model=RepairPatchResponse)
def get_repair_candidate_diff(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> RepairPatchResponse:
    """Retrieve a generated unified diff and its source hashes."""
    return repair_service.get_patch(db, candidate_id)


@router.patch("/repair-candidates/{candidate_id}/review", response_model=RepairCandidateResponse)
def review_repair_candidate(
    candidate_id: uuid.UUID,
    request: RepairCandidateReviewRequest,
    db: Session = Depends(get_db),
) -> RepairCandidateResponse:
    """Mark a candidate reviewed or rejected."""
    return repair_service.review_candidate(db, candidate_id, request.decision)
