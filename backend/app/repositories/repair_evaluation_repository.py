import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.repair_evaluation import RepairEvaluation
from app.repositories.base import BaseRepository


class RepairEvaluationRepository(BaseRepository[RepairEvaluation]):
    def __init__(self) -> None:
        super().__init__(RepairEvaluation)

    def get_for_candidate(
        self,
        db: Session,
        candidate_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[RepairEvaluation], int]:
        statement = select(RepairEvaluation).where(
            RepairEvaluation.repair_candidate_id == candidate_id
        )
        total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = db.scalars(
            statement.order_by(RepairEvaluation.created_at.desc(), RepairEvaluation.id)
            .offset(skip)
            .limit(limit)
        ).all()
        return items, total

    def has_active_evaluation(self, db: Session, candidate_id: uuid.UUID) -> bool:
        statement = select(RepairEvaluation.id).where(
            RepairEvaluation.repair_candidate_id == candidate_id,
            RepairEvaluation.status == "RUNNING",
        )
        return db.scalar(statement) is not None


repair_evaluation_repository = RepairEvaluationRepository()
