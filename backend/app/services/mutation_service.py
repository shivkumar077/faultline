import math
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidationException
from app.repositories.analysis_repository import analysis_repository
from app.repositories.mutation_repository import mutation_repository
from app.schemas.analysis_run import AnalysisRunDetailResponse
from app.schemas.common import PaginatedResponse
from app.schemas.mutation_record import GenerateMutationsRequest, MutationRecordResponse
from app.services.analysis_service import analysis_service
from app.services.mutation.ast_mutator import python_ast_mutator
from app.services.snapshot_materializer import snapshot_materializer
from app.services.snapshot_service import snapshot_service


class MutationService:
    def __init__(self):
        self.analysis_repo = analysis_repository
        self.mutation_repo = mutation_repository
        self.snapshot_svc = snapshot_service
        self.materializer = snapshot_materializer
        self.mutator = python_ast_mutator

    def generate_mutations(
        self,
        db: Session,
        snapshot_id: uuid.UUID,
        req: GenerateMutationsRequest,
    ) -> AnalysisRunDetailResponse:
        """Materialize snapshot, run AST mutators, persist records and manifest summary."""
        snapshot = self.snapshot_svc.get_snapshot_model(db, snapshot_id)

        if not snapshot.repository_connection:
            raise ValidationException(
                "Snapshot does not have an associated repository connection."
            )

        repo_url = snapshot.repository_connection.repository_url

        # Create initial AnalysisRun in running status
        analysis = self.analysis_repo.create(
            db,
            obj_in={
                "project_id": snapshot.project_id,
                "code_snapshot_id": snapshot.id,
                "name": f"AST Mutation Analysis - {snapshot.commit_hash[:7]}",
                "status": "running",
                "started_at": datetime.now(UTC),
            },
        )

        try:
            with self.materializer.materialized_workspace(
                repo_url, snapshot.commit_hash
            ) as workspace_dir:
                plan = self.mutator.generate_mutations(
                    workspace_dir=workspace_dir,
                    commit_hash=snapshot.commit_hash,
                    seed=req.seed,
                    max_mutations=req.max_mutations,
                )

            # Persist each candidate mutation as a MutationRecord
            for m in plan.mutations:
                self.mutation_repo.create(
                    db,
                    obj_in={
                        "analysis_run_id": analysis.id,
                        "mutation_type": m.mutation_type,
                        "target_file": m.target_file,
                        "line_number": m.line_number,
                        "original_code": m.original_code,
                        "mutated_code": m.mutated_code,
                        "status": "applied",
                    },
                )

            # Update AnalysisRun with final summary and completion timestamp
            analysis.status = "completed"
            analysis.completed_at = datetime.now(UTC)
            analysis.summary = plan.to_summary_dict()
            db.commit()

            return analysis_service.get_analysis(db, analysis.id)

        except Exception as exc:
            analysis.status = "failed"
            analysis.completed_at = datetime.now(UTC)
            analysis.summary = {"error": str(exc)}
            db.commit()
            raise

    def list_analysis_mutations(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[MutationRecordResponse]:
        """Return paginated mutation records for a specific analysis run."""
        analysis = self.analysis_repo.get(db, analysis_id)
        if not analysis:
            raise NotFoundException(resource="AnalysisRun", identifier=analysis_id)

        skip = (page - 1) * page_size
        items, total = self.mutation_repo.get_multi_by_analysis(
            db, analysis_id, skip=skip, limit=page_size
        )
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return PaginatedResponse[MutationRecordResponse](
            items=[MutationRecordResponse.model_validate(m) for m in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


mutation_service = MutationService()
