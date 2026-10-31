import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.baseline_execution import BaselineExecution
from app.models.failure_report import FailureReport
from app.models.mutation_record import MutationRecord
from app.repositories.base import BaseRepository


class AnalysisRepository(BaseRepository[AnalysisRun]):
    def __init__(self):
        super().__init__(AnalysisRun)

    def get_multi_by_project(
        self,
        db: Session,
        *,
        project_id: uuid.UUID | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[AnalysisRun], int]:
        total_stmt = select(func.count()).select_from(AnalysisRun)
        stmt = select(AnalysisRun)

        if project_id:
            total_stmt = total_stmt.where(AnalysisRun.project_id == project_id)
            stmt = stmt.where(AnalysisRun.project_id == project_id)

        if status:
            total_stmt = total_stmt.where(AnalysisRun.status == status)
            stmt = stmt.where(AnalysisRun.status == status)

        total = db.scalar(total_stmt) or 0
        items = list(
            db.scalars(stmt.order_by(AnalysisRun.created_at.desc()).offset(skip).limit(limit)).all()
        )
        return items, total

    def get_with_counts(
        self, db: Session, id: uuid.UUID
    ) -> tuple[AnalysisRun, int, int, int] | None:
        analysis = self.get(db, id)
        if not analysis:
            return None

        baseline_count = (
            db.scalar(
                select(func.count())
                .select_from(BaselineExecution)
                .where(BaselineExecution.analysis_run_id == id)
            )
            or 0
        )
        mutation_count = (
            db.scalar(
                select(func.count())
                .select_from(MutationRecord)
                .where(MutationRecord.analysis_run_id == id)
            )
            or 0
        )
        failure_count = (
            db.scalar(
                select(func.count())
                .select_from(FailureReport)
                .where(FailureReport.analysis_run_id == id)
            )
            or 0
        )

        return analysis, baseline_count, mutation_count, failure_count


analysis_repository = AnalysisRepository()
