import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import PaginatedResponse
from app.schemas.diagnosis import DiagnoseAnalysisRequest, DiagnosisRunResponse
from app.schemas.failure_report import FailureReportResponse
from app.services.diagnosis_service import failure_diagnosis_service

router = APIRouter(tags=["Diagnoses"])


@router.post(
    "/analyses/{analysis_id}/diagnose",
    response_model=DiagnosisRunResponse,
)
def diagnose_analysis(
    analysis_id: uuid.UUID,
    request: DiagnoseAnalysisRequest,
    db: Session = Depends(get_db),
) -> DiagnosisRunResponse:
    """Compare persisted mutant output with the analysis baseline and save reports."""
    return failure_diagnosis_service.diagnose_analysis(
        db,
        analysis_id,
        execution_ids=request.execution_ids,
    )


@router.get(
    "/analyses/{analysis_id}/diagnoses",
    response_model=PaginatedResponse[FailureReportResponse],
)
def list_analysis_diagnoses(
    analysis_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[FailureReportResponse]:
    """List persisted diagnosis reports for one analysis."""
    return failure_diagnosis_service.list_analysis_reports(
        db,
        analysis_id,
        page=page,
        page_size=page_size,
    )


@router.get("/diagnoses/{report_id}", response_model=FailureReportResponse)
def get_diagnosis(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FailureReportResponse:
    """Retrieve one diagnosis report by UUID."""
    return failure_diagnosis_service.get_report(db, report_id)
