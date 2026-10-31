"""Coordinate repair generation, candidate persistence, and review state."""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import FaultlineException, NotFoundException
from app.models.analysis_run import AnalysisRun
from app.models.failure_report import FailureReport
from app.models.repair_candidate import RepairCandidate
from app.repositories.analysis_repository import analysis_repository
from app.repositories.failure_report_repository import failure_report_repository
from app.repositories.repair_candidate_repository import (
    RepairCandidateRepository,
    repair_candidate_repository,
)
from app.schemas.common import PaginatedResponse
from app.schemas.repair_candidate import (
    RepairCandidateResponse,
    RepairCandidateSkip,
    RepairGenerationResponse,
    RepairPatchResponse,
)
from app.services.repair_patch_generator import (
    RepairGenerationRejected,
    RepairPatchGenerator,
)
from app.services.snapshot_materializer import SnapshotMaterializer, snapshot_materializer

logger = logging.getLogger("faultline.repair")


class RepairService:
    def __init__(
        self,
        *,
        materializer: SnapshotMaterializer | None = None,
        patch_generator: RepairPatchGenerator | None = None,
        candidates: RepairCandidateRepository | None = None,
    ):
        self.analysis_repo = analysis_repository
        self.report_repo = failure_report_repository
        self.candidate_repo = candidates or repair_candidate_repository
        self.materializer = materializer or snapshot_materializer
        self.patch_generator = patch_generator or RepairPatchGenerator()

    def generate_for_analysis(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        *,
        failure_report_ids: list[uuid.UUID] | None = None,
    ) -> RepairGenerationResponse:
        analysis = self._get_analysis(db, analysis_id)
        reports = list(self.report_repo.get_all_for_analysis(db, analysis_id))
        if failure_report_ids is not None:
            reports_by_id = {report.id: report for report in reports}
            missing = set(failure_report_ids) - reports_by_id.keys()
            if missing:
                raise FaultlineException(
                    status_code=422,
                    detail="One or more failure report IDs do not belong to this analysis.",
                    error_code="INVALID_FAILURE_REPORT_IDS",
                )
            selected = set(failure_report_ids)
            reports = [report for report in reports if report.id in selected]
        return self._generate(db, analysis, reports)

    def generate_for_diagnosis(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        failure_report_id: uuid.UUID,
    ) -> RepairGenerationResponse:
        analysis = self._get_analysis(db, analysis_id)
        report = self.report_repo.get(db, failure_report_id)
        if not report or report.analysis_run_id != analysis.id:
            raise NotFoundException("FailureReport", failure_report_id)
        return self._generate(db, analysis, [report])

    def list_for_analysis(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[RepairCandidateResponse]:
        self._get_analysis(db, analysis_id)
        items, total = self.candidate_repo.get_for_analysis(
            db,
            analysis_id,
            skip=(page - 1) * page_size,
            limit=page_size,
        )
        return PaginatedResponse[RepairCandidateResponse](
            items=[RepairCandidateResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 1,
        )

    def get_candidate(self, db: Session, candidate_id: uuid.UUID) -> RepairCandidateResponse:
        candidate = self.candidate_repo.get(db, candidate_id)
        if not candidate:
            raise NotFoundException("RepairCandidate", candidate_id)
        return RepairCandidateResponse.model_validate(candidate)

    def get_patch(self, db: Session, candidate_id: uuid.UUID) -> RepairPatchResponse:
        candidate = self.candidate_repo.get(db, candidate_id)
        if not candidate:
            raise NotFoundException("RepairCandidate", candidate_id)
        return RepairPatchResponse(
            repair_candidate_id=candidate.id,
            patch_content=candidate.patch_content,
            original_source_sha256=candidate.original_source_sha256,
            proposed_source_sha256=candidate.proposed_source_sha256,
        )

    def review_candidate(
        self,
        db: Session,
        candidate_id: uuid.UUID,
        decision: str,
    ) -> RepairCandidateResponse:
        candidate = self.candidate_repo.get(db, candidate_id)
        if not candidate:
            raise NotFoundException("RepairCandidate", candidate_id)
        if candidate.review_status == decision:
            return RepairCandidateResponse.model_validate(candidate)
        if candidate.review_status != "pending":
            raise FaultlineException(
                status_code=409,
                detail="A reviewed repair candidate cannot be changed to another decision.",
                error_code="REPAIR_CANDIDATE_ALREADY_REVIEWED",
            )
        reviewed_at = datetime.now(UTC)
        result = db.execute(
            update(RepairCandidate)
            .where(
                RepairCandidate.id == candidate_id,
                RepairCandidate.review_status == "pending",
            )
            .values(
                review_status=decision,
                reviewed_at=reviewed_at,
                updated_at=reviewed_at,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.rollback()
            candidate = self.candidate_repo.get(db, candidate_id)
            if candidate and candidate.review_status == decision:
                return RepairCandidateResponse.model_validate(candidate)
            raise FaultlineException(
                status_code=409,
                detail="A reviewed repair candidate cannot be changed to another decision.",
                error_code="REPAIR_CANDIDATE_ALREADY_REVIEWED",
            )
        db.commit()
        candidate = self.candidate_repo.get(db, candidate_id)
        if not candidate:
            raise NotFoundException("RepairCandidate", candidate_id)
        db.refresh(candidate)
        return RepairCandidateResponse.model_validate(candidate)

    def _generate(
        self,
        db: Session,
        analysis: AnalysisRun,
        reports: list[FailureReport],
    ) -> RepairGenerationResponse:
        snapshot = analysis.code_snapshot
        candidates: list[RepairCandidate] = []
        skipped: list[RepairCandidateSkip] = []
        pending: list[FailureReport] = []

        for report in reports:
            existing = self.candidate_repo.get_for_report_snapshot(db, report.id, snapshot.id)
            if existing:
                candidates.append(existing)
                continue
            try:
                self._validate_diagnosis(report, analysis.id)
                pending.append(report)
            except RepairGenerationRejected as exc:
                skipped.append(RepairCandidateSkip(failure_report_id=report.id, reason=exc.reason))

        if pending:
            connection = snapshot.repository_connection
            if connection is None:
                for report in pending:
                    skipped.append(
                        RepairCandidateSkip(
                            failure_report_id=report.id,
                            reason="snapshot_repository_unavailable",
                        )
                    )
            else:
                try:
                    with self.materializer.materialized_workspace(
                        connection.repository_url,
                        snapshot.commit_hash,
                    ) as workspace:
                        for report in pending:
                            try:
                                candidate = self._build_candidate(
                                    db,
                                    analysis,
                                    snapshot.id,
                                    snapshot.commit_hash,
                                    workspace,
                                    report,
                                )
                                candidates.append(candidate)
                            except RepairGenerationRejected as exc:
                                skipped.append(
                                    RepairCandidateSkip(
                                        failure_report_id=report.id,
                                        reason=exc.reason,
                                    )
                                )
                except FaultlineException as exc:
                    logger.error(
                        "Repair snapshot materialization failed (%s).",
                        exc.error_code,
                    )
                    raise FaultlineException(
                        status_code=503,
                        detail=(
                            "The analysis snapshot could not be materialized for repair generation."
                        ),
                        error_code="REPAIR_SNAPSHOT_MATERIALIZATION_FAILED",
                    ) from exc

        return RepairGenerationResponse(
            analysis_run_id=analysis.id,
            candidates=[
                RepairCandidateResponse.model_validate(candidate) for candidate in candidates
            ],
            skipped=skipped,
        )

    def _build_candidate(
        self,
        db: Session,
        analysis: AnalysisRun,
        snapshot_id: uuid.UUID,
        snapshot_commit: str,
        workspace: Path,
        report: FailureReport,
    ) -> RepairCandidate:
        mutation = report.mutation_record
        if mutation is None:
            raise RepairGenerationRejected("mutation_metadata_missing")
        if (
            mutation.analysis_run_id != analysis.id
            or report.mutation_file != mutation.target_file
            or report.original_expression != mutation.original_code
            or report.mutated_expression != mutation.mutated_code
            or mutation.status != "applied"
        ):
            raise RepairGenerationRejected("mutation_metadata_mismatch")
        patch = self.patch_generator.generate(workspace, mutation)
        draft = RepairCandidate(
            failure_report_id=report.id,
            analysis_run_id=analysis.id,
            code_snapshot_id=snapshot_id,
            mutation_record_id=mutation.id,
            snapshot_commit=snapshot_commit,
            target_file=patch.target_file,
            original_source_sha256=patch.original_source_sha256,
            proposed_source_sha256=patch.proposed_source_sha256,
            original_expression=patch.original_expression,
            replacement_expression=patch.replacement_expression,
            repair_strategy=patch.repair_strategy,
            explanation=(
                "Restores the recorded pre-mutation expression at its verified AST location. "
                "The patch passed syntax validation only; tests and repair correctness were "
                "not evaluated."
            ),
            evidence_references=[
                {
                    "failure_report_id": str(report.id),
                    "mutation_record_id": str(mutation.id),
                    "evidence_kind": item.get("kind"),
                }
                for item in report.evidence or []
                if isinstance(item, dict) and item.get("supports_cause") is True
            ],
            confidence_score=report.confidence_score or 0.0,
            patch_content=patch.patch_content,
            validation_status="syntax_valid",
            validation_error=None,
            review_status="pending",
        )
        return self._persist_candidate(db, draft)

    def _persist_candidate(
        self,
        db: Session,
        candidate: RepairCandidate,
    ) -> RepairCandidate:
        db.add(candidate)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            sqlite_conflict = (
                "unique constraint failed: repair_candidates.failure_report_id, "
                "repair_candidates.code_snapshot_id, repair_candidates.repair_strategy"
                in str(exc.orig).casefold()
            )
            if (
                constraint_name != "uq_repair_candidate_diagnosis_snapshot_strategy"
                and not sqlite_conflict
            ):
                raise
            existing = self.candidate_repo.get_for_report_snapshot(
                db,
                candidate.failure_report_id,
                candidate.code_snapshot_id,
            )
            if not existing:
                raise
            return existing
        db.refresh(candidate)
        return candidate

    def _get_analysis(self, db: Session, analysis_id: uuid.UUID) -> AnalysisRun:
        analysis = self.analysis_repo.get(db, analysis_id)
        if not analysis:
            raise NotFoundException("AnalysisRun", analysis_id)
        return analysis

    @staticmethod
    def _validate_diagnosis(report: FailureReport, analysis_id: uuid.UUID) -> None:
        if report.analysis_run_id != analysis_id:
            raise RepairGenerationRejected("diagnosis_analysis_mismatch")
        if report.category != "introduced_failure" or report.causal_attribution != "inferred":
            raise RepairGenerationRejected("unsupported_diagnosis")
        if not report.confidence_score or report.confidence_score < 0.55:
            raise RepairGenerationRejected("diagnosis_confidence_too_low")
        if not any(
            isinstance(item, dict) and item.get("supports_cause") is True
            for item in report.evidence or []
        ):
            raise RepairGenerationRejected("causal_evidence_missing")
        if not report.mutation_record_id:
            raise RepairGenerationRejected("mutation_metadata_missing")
        if (
            not report.mutation_file
            or not report.original_expression
            or not report.mutated_expression
        ):
            raise RepairGenerationRejected("mutation_metadata_incomplete")


repair_service = RepairService()
