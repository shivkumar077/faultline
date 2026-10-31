"""Repository for persisted mutant execution results."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.execution_result import ExecutionResult
from app.models.mutation_record import MutationRecord
from app.repositories.base import BaseRepository


class ExecutionResultRepository(BaseRepository[ExecutionResult]):
    def __init__(self):
        super().__init__(ExecutionResult)

    def get_by_analysis(self, db: Session, analysis_id: uuid.UUID) -> Sequence[ExecutionResult]:
        statement = (
            select(ExecutionResult)
            .join(MutationRecord)
            .where(MutationRecord.analysis_run_id == analysis_id)
            .order_by(ExecutionResult.created_at, ExecutionResult.id)
        )
        return db.scalars(statement).all()

    def get_by_analysis_and_id(
        self, db: Session, analysis_id: uuid.UUID, result_id: uuid.UUID
    ) -> ExecutionResult | None:
        statement = (
            select(ExecutionResult)
            .join(MutationRecord)
            .where(
                MutationRecord.analysis_run_id == analysis_id,
                ExecutionResult.id == result_id,
            )
        )
        return db.scalar(statement)


execution_result_repository = ExecutionResultRepository()
