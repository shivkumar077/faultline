import math
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.repositories.analysis_repository import analysis_repository
from app.schemas.analysis_run import AnalysisRunDetailResponse, AnalysisRunResponse
from app.schemas.common import PaginatedResponse


class AnalysisService:
    def __init__(self):
        self.repo = analysis_repository

    def list_analyses(
        self,
        db: Session,
        *,
        project_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[AnalysisRunResponse]:
        skip = (page - 1) * page_size
        items, total = self.repo.get_multi_by_project(
            db, project_id=project_id, status=status, skip=skip, limit=page_size
        )
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return PaginatedResponse[AnalysisRunResponse](
            items=[AnalysisRunResponse.model_validate(a) for a in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def get_analysis(self, db: Session, analysis_id: uuid.UUID) -> AnalysisRunDetailResponse:
        result = self.repo.get_with_counts(db, analysis_id)
        if not result:
            raise NotFoundException(resource="AnalysisRun", identifier=analysis_id)

        analysis, baseline_count, mutation_count, failure_count = result
        response = AnalysisRunDetailResponse.model_validate(analysis)
        response.baseline_executions_count = baseline_count
        response.mutation_records_count = mutation_count
        response.failure_reports_count = failure_count
        return response


analysis_service = AnalysisService()
