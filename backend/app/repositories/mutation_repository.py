import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.mutation_record import MutationRecord
from app.repositories.base import BaseRepository


class MutationRepository(BaseRepository[MutationRecord]):
    def __init__(self):
        super().__init__(MutationRecord)

    def get_multi_by_analysis(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[MutationRecord], int]:
        total = (
            db.scalar(
                select(func.count())
                .select_from(MutationRecord)
                .where(MutationRecord.analysis_run_id == analysis_id)
            )
            or 0
        )
        stmt = (
            select(MutationRecord)
            .where(MutationRecord.analysis_run_id == analysis_id)
            .order_by(
                MutationRecord.target_file.asc(),
                MutationRecord.line_number.asc(),
                MutationRecord.created_at.asc(),
            )
            .offset(skip)
            .limit(limit)
        )
        records = db.scalars(stmt).all()
        return records, total


mutation_repository = MutationRepository()
