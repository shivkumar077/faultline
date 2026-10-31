"""Persistence queries for generated repair candidates."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.repair_candidate import RepairCandidate
from app.repositories.base import BaseRepository


class RepairCandidateRepository(BaseRepository[RepairCandidate]):
    def __init__(self):
        super().__init__(RepairCandidate)

    def get_for_report_snapshot(
        self,
        db: Session,
        failure_report_id: uuid.UUID,
        code_snapshot_id: uuid.UUID,
    ) -> RepairCandidate | None:
        statement = select(RepairCandidate).where(
            RepairCandidate.failure_report_id == failure_report_id,
            RepairCandidate.code_snapshot_id == code_snapshot_id,
        )
        return db.scalars(statement).first()

    def get_for_analysis(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[RepairCandidate], int]:
        statement = select(RepairCandidate).where(RepairCandidate.analysis_run_id == analysis_id)
        total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = db.scalars(
            statement.order_by(RepairCandidate.created_at, RepairCandidate.id)
            .offset(skip)
            .limit(limit)
        ).all()
        return items, total


repair_candidate_repository = RepairCandidateRepository()
