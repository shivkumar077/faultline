"""Repository for BaselineExecution database operations."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.baseline_execution import BaselineExecution
from app.repositories.base import BaseRepository


class BaselineExecutionRepository(BaseRepository[BaselineExecution]):
    def __init__(self):
        super().__init__(BaselineExecution)

    def get_by_analysis(self, db: Session, analysis_id: uuid.UUID) -> BaselineExecution | None:
        """Retrieve the latest baseline execution record for an analysis run."""
        stmt = (
            select(BaselineExecution)
            .where(BaselineExecution.analysis_run_id == analysis_id)
            .order_by(BaselineExecution.created_at.desc())
            .limit(1)
        )
        return db.scalar(stmt)

    def get_multi_by_analysis(
        self, db: Session, analysis_id: uuid.UUID
    ) -> Sequence[BaselineExecution]:
        """Retrieve all baseline execution records for an analysis run."""
        stmt = (
            select(BaselineExecution)
            .where(BaselineExecution.analysis_run_id == analysis_id)
            .order_by(BaselineExecution.created_at.desc())
        )
        return db.scalars(stmt).all()


baseline_execution_repository = BaselineExecutionRepository()
