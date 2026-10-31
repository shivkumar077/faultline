"""Persistence queries for failure diagnosis reports."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.failure_report import FailureReport
from app.repositories.base import BaseRepository


class FailureReportRepository(BaseRepository[FailureReport]):
    def __init__(self):
        super().__init__(FailureReport)

    def get_for_analysis(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[FailureReport], int]:
        statement = select(FailureReport).where(FailureReport.analysis_run_id == analysis_id)
        total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = db.scalars(
            statement.order_by(FailureReport.created_at, FailureReport.id).offset(skip).limit(limit)
        ).all()
        return items, total

    def get_by_diagnosis_keys(
        self,
        db: Session,
        diagnosis_keys: list[str],
    ) -> dict[str, FailureReport]:
        if not diagnosis_keys:
            return {}
        statement = select(FailureReport).where(FailureReport.diagnosis_key.in_(diagnosis_keys))
        return {
            report.diagnosis_key: report for report in db.scalars(statement) if report.diagnosis_key
        }

    def get_all_for_analysis(self, db: Session, analysis_id: uuid.UUID) -> Sequence[FailureReport]:
        statement = (
            select(FailureReport)
            .where(FailureReport.analysis_run_id == analysis_id)
            .order_by(FailureReport.created_at, FailureReport.id)
        )
        return db.scalars(statement).all()


failure_report_repository = FailureReportRepository()
