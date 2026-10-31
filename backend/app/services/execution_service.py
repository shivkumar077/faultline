"""Persisted baseline and mutant execution workflow."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import FaultlineException, NotFoundException, ValidationException
from app.models.analysis_run import AnalysisRun
from app.models.baseline_execution import BaselineExecution
from app.models.execution_result import ExecutionResult
from app.models.mutation_record import MutationRecord
from app.repositories.analysis_repository import analysis_repository
from app.repositories.baseline_execution_repository import baseline_execution_repository
from app.repositories.execution_result_repository import execution_result_repository
from app.repositories.mutation_repository import mutation_repository
from app.schemas.baseline_execution import BaselineExecutionResponse
from app.schemas.common import PaginatedResponse
from app.schemas.execution import (
    ExecuteAnalysisResponse,
    ExecutionRecordResponse,
)
from app.schemas.execution_result import ExecutionResultResponse
from app.services.execution_metrics import classify_mutation, summarize_mutations
from app.services.sandbox.baseline_runner import (
    BaselineRunner,
    baseline_runner,
    parse_test_counts,
)
from app.services.sandbox.docker_runtime import DockerRuntime, docker_runtime
from app.services.sandbox.mutation_applicator import MutationApplicator, mutation_applicator
from app.services.snapshot_materializer import SnapshotMaterializer, snapshot_materializer

logger = logging.getLogger("faultline.execution")


class ExecutionService:
    def __init__(
        self,
        *,
        runner: BaselineRunner | None = None,
        runtime: DockerRuntime | None = None,
        materializer: SnapshotMaterializer | None = None,
        applicator: MutationApplicator | None = None,
    ):
        self.analysis_repo = analysis_repository
        self.baseline_repo = baseline_execution_repository
        self.result_repo = execution_result_repository
        self.mutation_repo = mutation_repository
        self.runner = runner or baseline_runner
        self.runtime = runtime or docker_runtime
        self.materializer = materializer or snapshot_materializer
        self.applicator = applicator or mutation_applicator

    def execute_analysis(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        *,
        timeout_seconds: int | None = None,
    ) -> ExecuteAnalysisResponse:
        analysis = self.analysis_repo.get(db, analysis_id)
        if not analysis:
            raise NotFoundException("AnalysisRun", analysis_id)
        if analysis.status == "running" or self.baseline_repo.exists_for_analysis(db, analysis_id):
            raise FaultlineException(
                status_code=409,
                detail="Execution has already started for this analysis.",
                error_code="EXECUTION_ALREADY_STARTED",
            )
        if analysis.status != "completed":
            raise ValidationException("Only a completed mutation analysis can be executed.")

        snapshot = analysis.code_snapshot
        connection = snapshot.repository_connection
        if connection is None:
            raise ValidationException("Analysis snapshot has no repository connection.")

        started = datetime.now(UTC)
        analysis.status = "running"
        analysis.started_at = started
        baseline = BaselineExecution(
            analysis_run_id=analysis.id,
            code_snapshot_id=snapshot.id,
            command="approved-test-runner",
            command_identifier="pending",
            framework="none",
            status="running",
        )
        db.add(baseline)
        mutations = self.mutation_repo.get_all_by_analysis(db, analysis.id)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise FaultlineException(
                status_code=409,
                detail="Execution has already started for this analysis.",
                error_code="EXECUTION_ALREADY_STARTED",
            ) from exc

        try:
            with self.materializer.materialized_workspace(
                connection.repository_url, snapshot.commit_hash
            ) as baseline_workspace:
                baseline_output = self.runner.run_baseline(
                    baseline_workspace, timeout_seconds=timeout_seconds
                )
        except Exception as exc:
            code = self._error_code(exc, "BASELINE_INFRASTRUCTURE_ERROR")
            self._finish_baseline_error(db, analysis, baseline, code, len(mutations))
            if isinstance(exc, FaultlineException):
                raise
            logger.error("Baseline infrastructure failed (%s)", type(exc).__name__)
            raise FaultlineException(
                status_code=503,
                detail="Baseline execution could not be completed.",
                error_code=code,
            ) from exc

        baseline.command = baseline_output.command[:512]
        baseline.command_identifier = baseline_output.framework
        baseline.framework = baseline_output.framework
        baseline.test_files_count = baseline_output.test_files_count
        baseline.status = baseline_output.status
        baseline.exit_code = baseline_output.exit_code
        baseline.stdout = baseline_output.stdout
        baseline.stderr = baseline_output.stderr
        baseline.duration_ms = baseline_output.duration_ms
        baseline.passed_count = baseline_output.passed_count
        baseline.failed_count = baseline_output.failed_count
        baseline.skipped_count = baseline_output.skipped_count
        baseline.timed_out = baseline_output.timed_out
        baseline.infrastructure_error = baseline_output.infrastructure_error
        if baseline.status == "error" and not baseline.infrastructure_error:
            baseline.infrastructure_error = "BASELINE_EXECUTION_FAILED"

        if baseline.status != "passed":
            summary = self._summary(len(mutations), [])
            summary["baseline_status"] = baseline.status
            summary["baseline_error"] = baseline.infrastructure_error
            analysis.summary = {**(analysis.summary or {}), **summary}
            analysis.status = "failed"
            analysis.completed_at = datetime.now(UTC)
            db.commit()
            return self._response(db, analysis, baseline, [])

        results: list[ExecutionResult] = []
        command = (
            ("python", "-m", "unittest", "discover", "-s", ".", "-p", "test*.py")
            if baseline.framework == "unittest"
            else (
                "python",
                "-m",
                "pytest",
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            )
        )

        for mutation in mutations:
            result = ExecutionResult(
                mutation_record_id=mutation.id,
                status="running",
                mutation_application_status="pending",
            )
            db.add(result)
            db.commit()
            self._run_mutation(
                db,
                result,
                mutation,
                analysis,
                connection.repository_url,
                snapshot.commit_hash,
                command,
                timeout_seconds,
                baseline.framework,
            )
            results.append(result)

        summary = self._summary(len(mutations), results)
        summary["baseline_status"] = baseline.status
        analysis.summary = {**(analysis.summary or {}), **summary}
        analysis.status = "completed"
        analysis.completed_at = datetime.now(UTC)
        db.commit()
        return self._response(db, analysis, baseline, results)

    def list_executions(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[ExecutionRecordResponse]:
        analysis = self.analysis_repo.get(db, analysis_id)
        if not analysis:
            raise NotFoundException("AnalysisRun", analysis_id)

        records: list[ExecutionRecordResponse] = []
        baseline_runs = self.baseline_repo.get_multi_by_analysis(db, analysis_id)
        results = self.result_repo.get_by_analysis(db, analysis_id)
        records.extend(self._baseline_record(analysis_id, run) for run in baseline_runs)
        records.extend(self._result_record(analysis_id, result) for result in results)
        records.sort(key=lambda item: str(item.id))
        total = len(records)
        start = (page - 1) * page_size
        total_pages = (total + page_size - 1) // page_size if total else 1
        return PaginatedResponse[ExecutionRecordResponse](
            items=records[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def get_execution(self, db: Session, execution_id: uuid.UUID) -> ExecutionRecordResponse:
        baseline = self.baseline_repo.get(db, execution_id)
        if baseline:
            return self._baseline_record(baseline.analysis_run_id, baseline)
        result = self.result_repo.get(db, execution_id)
        if result:
            analysis_id = result.mutation_record.analysis_run_id
            return self._result_record(analysis_id, result)
        raise NotFoundException("Execution", execution_id)

    def _run_mutation(
        self,
        db: Session,
        result: ExecutionResult,
        mutation: MutationRecord,
        analysis: AnalysisRun,
        repository_url: str,
        commit_hash: str,
        command: tuple[str, ...],
        timeout_seconds: int | None,
        framework: str,
    ) -> None:
        col_offset, source_sha256 = self._mutation_source_metadata(analysis, mutation)
        if source_sha256 is None:
            result.status = "INVALID"
            result.mutation_application_status = "invalid"
            result.stderr = "Mutation manifest is missing source validation metadata."
            db.commit()
            return

        try:
            with self.materializer.materialized_workspace(repository_url, commit_hash) as workspace:
                try:
                    self.applicator.apply_mutation(
                        workspace_path=workspace,
                        target_file=mutation.target_file,
                        line_number=mutation.line_number,
                        col_offset=col_offset,
                        original_code=mutation.original_code,
                        mutated_code=mutation.mutated_code,
                        source_sha256=source_sha256,
                    )
                except ValidationException:
                    result.status = "INVALID"
                    result.mutation_application_status = "invalid"
                    result.stderr = "Mutation did not match or validate against the exact snapshot."
                    db.commit()
                    return
                result.mutation_application_status = "applied"
                output = self.runtime.run_in_container(
                    workspace,
                    list(command),
                    timeout_seconds=timeout_seconds,
                )

            result.exit_code = output.exit_code
            result.stdout = output.stdout
            result.stderr = output.stderr
            result.duration_ms = output.duration_ms
            result.timed_out = output.timed_out
            result.test_output = {
                "framework": framework,
                **parse_test_counts(f"{output.stdout}\n{output.stderr}"),
            }
            result.status, result.infrastructure_error = classify_mutation(
                exit_code=output.exit_code,
                timed_out=output.timed_out,
                output_limited=output.output_limited,
                mutation_applied=True,
            )
        except Exception as exc:
            result.status = "ERROR"
            result.infrastructure_error = self._error_code(exc, "MUTANT_INFRASTRUCTURE_ERROR")
            result.mutation_application_status = (
                "error" if result.mutation_application_status == "pending" else "applied"
            )
            result.stderr = (
                "Mutant execution could not be completed due to an infrastructure error."
            )
            logger.error("Mutant execution failed (%s)", type(exc).__name__)
        db.commit()

    @staticmethod
    def _mutation_source_metadata(
        analysis: AnalysisRun, mutation: MutationRecord
    ) -> tuple[int | None, str | None]:
        col_offset = mutation.col_offset
        source_hash = mutation.source_sha256
        summary = analysis.summary or {}
        file_hashes = summary.get("file_hashes")
        if source_hash is None and isinstance(file_hashes, dict):
            candidate_hash = file_hashes.get(mutation.target_file)
            if isinstance(candidate_hash, str):
                source_hash = candidate_hash

        manifest = summary.get("manifest")
        if col_offset is None and isinstance(manifest, list):
            matches = [
                entry
                for entry in manifest
                if isinstance(entry, dict)
                and entry.get("target_file") == mutation.target_file
                and entry.get("line_number") == mutation.line_number
                and entry.get("mutation_type") == mutation.mutation_type
                and entry.get("original_code") == mutation.original_code
                and entry.get("mutated_code") == mutation.mutated_code
            ]
            if len(matches) > 1:
                return None, None
            if len(matches) == 1 and isinstance(matches[0].get("col_offset"), int):
                col_offset = matches[0]["col_offset"]
        return col_offset, source_hash

    @staticmethod
    def _summary(total: int, results: list[ExecutionResult]) -> dict[str, int | float | None]:
        return summarize_mutations(total, (item.status for item in results))

    @staticmethod
    def _error_code(exc: Exception, fallback: str) -> str:
        if isinstance(exc, FaultlineException):
            return exc.error_code
        return fallback

    @staticmethod
    def _finish_baseline_error(
        db: Session,
        analysis: AnalysisRun,
        baseline: BaselineExecution,
        error_code: str,
        total_mutations: int,
    ) -> None:
        baseline.status = "error"
        baseline.infrastructure_error = error_code
        baseline.stderr = "Baseline execution could not be completed due to infrastructure failure."
        analysis.status = "failed"
        analysis.completed_at = datetime.now(UTC)
        analysis.summary = {
            **(analysis.summary or {}),
            **ExecutionService._summary(total_mutations, []),
            "baseline_status": "error",
            "baseline_error": error_code,
        }
        db.commit()

    def _response(
        self,
        db: Session,
        analysis: AnalysisRun,
        baseline: BaselineExecution,
        results: list[ExecutionResult],
    ) -> ExecuteAnalysisResponse:
        db.refresh(baseline)
        return ExecuteAnalysisResponse(
            analysis_run_id=analysis.id,
            status=analysis.status,
            baseline=BaselineExecutionResponse.model_validate(baseline),
            execution_results=[
                ExecutionResultResponse.model_validate(db.refresh(result) or result)
                for result in results
            ],
            summary=analysis.summary or {},
        )

    @staticmethod
    def _baseline_record(
        analysis_id: uuid.UUID, baseline: BaselineExecution
    ) -> ExecutionRecordResponse:
        return ExecutionRecordResponse(
            id=baseline.id,
            analysis_run_id=analysis_id,
            kind="baseline",
            status=baseline.status,
            exit_code=baseline.exit_code,
            duration_ms=baseline.duration_ms,
            stdout=baseline.stdout,
            stderr=baseline.stderr,
            timed_out=baseline.timed_out,
            infrastructure_error=baseline.infrastructure_error,
        )

    @staticmethod
    def _result_record(analysis_id: uuid.UUID, result: ExecutionResult) -> ExecutionRecordResponse:
        return ExecutionRecordResponse(
            id=result.id,
            analysis_run_id=analysis_id,
            kind="mutation",
            mutation_record_id=result.mutation_record_id,
            status=result.status,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
            infrastructure_error=result.infrastructure_error,
        )


execution_service = ExecutionService()
