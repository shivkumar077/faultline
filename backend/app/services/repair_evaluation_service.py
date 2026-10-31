"""Safely apply persisted repair patches and evaluate them in the Docker runner."""

import ast
import hashlib
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import FaultlineException, NotFoundException
from app.core.sandbox_config import sandbox_config
from app.models.baseline_execution import BaselineExecution
from app.models.execution_result import ExecutionResult
from app.models.failure_report import FailureReport
from app.models.mutation_record import MutationRecord
from app.models.repair_candidate import RepairCandidate
from app.models.repair_evaluation import RepairEvaluation
from app.repositories.baseline_execution_repository import baseline_execution_repository
from app.repositories.repair_candidate_repository import repair_candidate_repository
from app.repositories.repair_evaluation_repository import (
    RepairEvaluationRepository,
    repair_evaluation_repository,
)
from app.schemas.common import PaginatedResponse
from app.schemas.repair_evaluation import (
    RepairEvaluationRequest,
    RepairEvaluationResponse,
    RepairEvaluationStatus,
)
from app.services.diagnosis_parser import ParsedTestOutput, parse_failure_output
from app.services.forgefit_adapter import ForgeFitAdapter, forgefit_adapter
from app.services.sandbox.baseline_runner import (
    BaselineRunner,
    BaselineRunOutput,
    baseline_runner,
)
from app.services.sandbox.docker_runtime import DockerRuntime
from app.services.snapshot_materializer import SnapshotMaterializer, snapshot_materializer

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")
_SUPPORTED_DIAGNOSIS = "introduced_failure"
_STATUS_INVALID = "INVALID"
_MAX_FAILURE_IDS = 500


class EvaluationRejected(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class RepairEvaluationService:
    def __init__(
        self,
        *,
        runner: BaselineRunner | None = None,
        materializer: SnapshotMaterializer | None = None,
        forgefit: ForgeFitAdapter | None = None,
        evaluations: RepairEvaluationRepository | None = None,
    ) -> None:
        self.runner = runner or baseline_runner
        self.materializer = materializer or snapshot_materializer
        self.forgefit = forgefit or forgefit_adapter
        self.evaluations = evaluations or repair_evaluation_repository

    def evaluate_candidate(
        self,
        db: Session,
        candidate_id: uuid.UUID,
        request: RepairEvaluationRequest,
    ) -> RepairEvaluationResponse:
        candidate = repair_candidate_repository.get(db, candidate_id)
        if not candidate:
            raise NotFoundException("RepairCandidate", candidate_id)
        if candidate.review_status == "rejected":
            raise FaultlineException(
                status_code=409,
                detail="Rejected repair candidates cannot be evaluated.",
                error_code="REPAIR_CANDIDATE_REJECTED",
            )
        if self.evaluations.has_active_evaluation(db, candidate_id):
            raise FaultlineException(
                status_code=409,
                detail="An evaluation is already running for this candidate.",
                error_code="REPAIR_EVALUATION_IN_PROGRESS",
            )

        report = db.get(FailureReport, candidate.failure_report_id)
        baseline = self._get_baseline(db, candidate, report)
        mutant_result = (
            db.get(ExecutionResult, report.execution_result_id)
            if report and report.execution_result_id
            else None
        )
        evaluation = RepairEvaluation(
            repair_candidate_id=candidate.id,
            analysis_run_id=candidate.analysis_run_id,
            failure_report_id=candidate.failure_report_id,
            baseline_execution_id=baseline.id if baseline else None,
            mutant_execution_result_id=mutant_result.id if mutant_result else None,
            status="RUNNING",
            evidence={},
            forgefit_status="not_requested",
        )
        db.add(evaluation)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            sqlite_conflict = (
                "unique constraint failed: repair_evaluations.repair_candidate_id"
                in str(exc.orig).casefold()
            )
            if constraint_name != "uq_repair_evaluations_active_candidate" and not sqlite_conflict:
                raise
            raise FaultlineException(
                status_code=409,
                detail="An evaluation is already running for this candidate.",
                error_code="REPAIR_EVALUATION_IN_PROGRESS",
            ) from exc
        db.refresh(evaluation)

        invalid_reason = self._eligibility_error(candidate, report, baseline, mutant_result)
        if invalid_reason:
            evaluation.status = _STATUS_INVALID
            evaluation.error_code = invalid_reason
            evaluation.evidence = {
                "classification": "invalid_evaluation_input",
                "baseline_status": baseline.status if baseline else None,
                "diagnosis_category": report.category if report else None,
                "baseline_failure_ids": (
                    _failure_ids(
                        parse_failure_output(baseline.stdout, baseline.stderr, baseline.framework)
                    )
                    if baseline and baseline.status != "passed"
                    else []
                ),
                "mutant_failure_ids": (
                    _failure_ids(
                        parse_failure_output(
                            mutant_result.stdout,
                            mutant_result.stderr,
                            baseline.framework if baseline else None,
                        )
                    )
                    if mutant_result
                    else []
                ),
                "candidate_attribution_performed": False,
            }
            self._complete(db, evaluation)
            return RepairEvaluationResponse.model_validate(evaluation)

        if report is None or baseline is None or mutant_result is None:
            evaluation.status = _STATUS_INVALID
            evaluation.error_code = "REQUIRED_EVALUATION_EVIDENCE_MISSING"
            evaluation.evidence = {"classification": "invalid_evaluation_input"}
            self._complete(db, evaluation)
            return RepairEvaluationResponse.model_validate(evaluation)
        analysis = candidate.analysis_run
        snapshot = analysis.code_snapshot
        connection = snapshot.repository_connection
        if connection is None:
            evaluation.status = _STATUS_INVALID
            evaluation.error_code = "SNAPSHOT_REPOSITORY_UNAVAILABLE"
            evaluation.evidence = {"classification": "invalid_evaluation_input"}
            self._complete(db, evaluation)
            return RepairEvaluationResponse.model_validate(evaluation)

        run: BaselineRunOutput | None = None
        try:
            with self.materializer.materialized_workspace(
                connection.repository_url,
                candidate.snapshot_commit,
            ) as source_workspace:
                status, error_code, run, evidence = self._evaluate_in_workspace(
                    source_workspace,
                    candidate,
                    report,
                    baseline,
                    mutant_result,
                    request.timeout_seconds,
                )
            evaluation.status = status
            evaluation.error_code = error_code
            evaluation.exit_code = run.exit_code if run else None
            evaluation.duration_ms = run.duration_ms if run else None
            evaluation.passed_count = run.passed_count if run else None
            evaluation.failed_count = run.failed_count if run else None
            evaluation.skipped_count = run.skipped_count if run else None
            evaluation.evidence = evidence
        except EvaluationRejected as exc:
            evaluation.status = _STATUS_INVALID
            evaluation.error_code = exc.code
            evaluation.evidence = {"classification": "invalid_patch"}
        except FaultlineException as exc:
            evaluation.status = "ERROR"
            evaluation.error_code = exc.error_code
            evaluation.evidence = {"classification": "execution_infrastructure_error"}
        except OSError:
            evaluation.status = "ERROR"
            evaluation.error_code = "WORKSPACE_IO_ERROR"
            evaluation.evidence = {"classification": "workspace_io_error"}

        if request.forgefit_scenario is not None:
            outcome = self.forgefit.run_scenario(
                request.forgefit_scenario,
                candidate_id=candidate.id,
                evaluation_id=evaluation.id,
            )
            evaluation.forgefit_status = outcome.status
            evaluation.forgefit_run_id = outcome.run_id
            evaluation.forgefit_result = outcome.result
            evaluation.forgefit_error_code = outcome.error_code

        self._complete(db, evaluation)
        return RepairEvaluationResponse.model_validate(evaluation)

    def list_for_candidate(
        self,
        db: Session,
        candidate_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[RepairEvaluationResponse]:
        if not repair_candidate_repository.get(db, candidate_id):
            raise NotFoundException("RepairCandidate", candidate_id)
        items, total = self.evaluations.get_for_candidate(
            db,
            candidate_id,
            skip=(page - 1) * page_size,
            limit=page_size,
        )
        return PaginatedResponse[RepairEvaluationResponse](
            items=[RepairEvaluationResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total else 1,
        )

    def get_evaluation(
        self,
        db: Session,
        evaluation_id: uuid.UUID,
    ) -> RepairEvaluationResponse:
        evaluation = self.evaluations.get(db, evaluation_id)
        if not evaluation:
            raise NotFoundException("RepairEvaluation", evaluation_id)
        return RepairEvaluationResponse.model_validate(evaluation)

    @staticmethod
    def _get_baseline(
        db: Session,
        candidate: RepairCandidate,
        report: FailureReport | None,
    ) -> BaselineExecution | None:
        if report and report.baseline_execution_id:
            return db.get(BaselineExecution, report.baseline_execution_id)
        return baseline_execution_repository.get_by_analysis(db, candidate.analysis_run_id)

    @staticmethod
    def _eligibility_error(
        candidate: RepairCandidate,
        report: FailureReport | None,
        baseline: BaselineExecution | None,
        mutant_result: ExecutionResult | None,
    ) -> str | None:
        if candidate.validation_status != "syntax_valid":
            return "CANDIDATE_NOT_SYNTAX_VALID"
        if not report or report.analysis_run_id != candidate.analysis_run_id:
            return "DIAGNOSIS_NOT_FOUND"
        if report.category != _SUPPORTED_DIAGNOSIS:
            return "UNSUPPORTED_DIAGNOSIS"
        if not baseline or baseline.analysis_run_id != candidate.analysis_run_id:
            return "BASELINE_NOT_FOUND"
        if (
            baseline.code_snapshot_id != candidate.code_snapshot_id
            or candidate.code_snapshot_id != candidate.analysis_run.code_snapshot_id
        ):
            return "SNAPSHOT_MISMATCH"
        if baseline.status != "passed":
            return "BASELINE_NOT_PASSED"
        if not mutant_result or mutant_result.status != "failed":
            return "MUTANT_FAILURE_NOT_FOUND"
        if mutant_result.mutation_record_id != candidate.mutation_record_id:
            return "MUTANT_EXECUTION_MISMATCH"
        if (
            report.causal_attribution != "inferred"
            or report.confidence_score is None
            or report.confidence_score < 0.55
            or not any(
                isinstance(item, dict) and item.get("supports_cause") is True
                for item in report.evidence or []
            )
        ):
            return "DIAGNOSIS_EVIDENCE_INSUFFICIENT"
        if baseline.framework not in {"pytest", "unittest"}:
            return "UNSUPPORTED_TEST_FRAMEWORK"
        if (
            candidate.snapshot_commit != candidate.analysis_run.code_snapshot.commit_hash
            or candidate.code_snapshot_id != candidate.analysis_run.code_snapshot_id
        ):
            return "SNAPSHOT_COMMIT_MISMATCH"
        if candidate.repair_strategy not in {
            "exact_mutation_reversal",
            "ast_expression_restoration",
        }:
            return "UNSUPPORTED_REPAIR_STRATEGY"
        return None

    def _evaluate_in_workspace(
        self,
        source_workspace: Path,
        candidate: RepairCandidate,
        report: FailureReport,
        baseline: BaselineExecution,
        mutant_result: ExecutionResult,
        timeout_seconds: int | None,
    ) -> tuple[
        RepairEvaluationStatus,
        str | None,
        BaselineRunOutput,
        dict[str, object],
    ]:
        source_path = self._resolve_target(source_workspace, candidate.target_file)
        self._validate_candidate_metadata(candidate, report)
        source = self._read_normalized_source(source_path)
        source_hash = _sha256(source.encode("utf-8"))
        if source_hash != candidate.original_source_sha256:
            raise EvaluationRejected("ORIGINAL_SOURCE_HASH_MISMATCH")

        mutation = candidate.mutation_record
        if mutation is None:
            raise EvaluationRejected("MUTATION_METADATA_MISSING")
        if mutation.source_sha256 != source_hash:
            raise EvaluationRejected("MUTATION_SOURCE_HASH_MISMATCH")
        try:
            original_tree = ast.parse(source, filename=candidate.target_file)
        except SyntaxError:
            raise EvaluationRejected("ORIGINAL_SOURCE_SYNTAX_INVALID") from None
        self._verify_ast_target(original_tree, mutation, candidate)
        proposed = _apply_unified_patch(candidate.patch_content, source, candidate.target_file)
        if _sha256(proposed.encode("utf-8")) != candidate.proposed_source_sha256:
            raise EvaluationRejected("PROPOSED_SOURCE_HASH_MISMATCH")
        try:
            ast.parse(proposed, filename=candidate.target_file)
        except SyntaxError:
            raise EvaluationRejected("PATCH_SOURCE_SYNTAX_INVALID") from None

        with tempfile.TemporaryDirectory(prefix="faultline_repair_eval_") as temp_dir:
            candidate_workspace = Path(temp_dir) / "candidate"
            shutil.copytree(source_workspace, candidate_workspace, symlinks=True)
            candidate_path = self._resolve_target(candidate_workspace, candidate.target_file)
            candidate_path.write_text(proposed, encoding="utf-8", newline="")
            if _sha256(self._read_normalized_source(candidate_path).encode("utf-8")) != (
                candidate.proposed_source_sha256
            ):
                raise EvaluationRejected("WRITTEN_SOURCE_HASH_MISMATCH")

            command = (
                ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider"]
                if baseline.framework == "pytest"
                else ["python", "-m", "unittest", "discover", "-s", ".", "-p", "test*.py"]
            )
            if tuple(command) not in DockerRuntime.APPROVED_COMMANDS:
                raise EvaluationRejected("UNAPPROVED_TEST_COMMAND")
            run = self.runner.run_baseline(
                candidate_workspace,
                custom_command=command,
                timeout_seconds=timeout_seconds or sandbox_config.timeout_seconds,
            )

        status = self._classify_run(run.status, run.timed_out, run.infrastructure_error)
        baseline_output = parse_failure_output(
            baseline.stdout,
            baseline.stderr,
            baseline.framework,
        )
        mutant_output = parse_failure_output(
            mutant_result.stdout,
            mutant_result.stderr,
            baseline.framework,
        )
        candidate_output = parse_failure_output(run.stdout, run.stderr, baseline.framework)
        diagnosed_test = report.test_identifier or report.affected_test
        candidate_failure_ids = _failure_ids(candidate_output)
        baseline_failure_ids = _failure_ids(baseline_output)
        mutant_failure_ids = _failure_ids(mutant_output)
        passed_ids = {_safe_test_identifier(item) for item in candidate_output.passed_test_ids}
        diagnosed_state = "unknown"
        if diagnosed_test:
            safe_diagnosed = _safe_test_identifier(diagnosed_test)
            if _matches_test_id(safe_diagnosed, candidate_failure_ids):
                diagnosed_state = "still_failing"
            elif _matches_test_id(safe_diagnosed, sorted(passed_ids)):
                diagnosed_state = "observed_passed"
            else:
                diagnosed_state = "not_observed"
        output_truncated = "[output truncated]" in run.stdout or "[output truncated]" in run.stderr
        if status == "FAILED" and diagnosed_state == "observed_passed":
            status = "PARTIALLY_PASSED"
        elif status == "PASSED":
            baseline_total = _test_total(
                baseline.passed_count,
                baseline.failed_count,
                baseline.skipped_count,
            )
            candidate_total = _test_total(run.passed_count, run.failed_count, run.skipped_count)
            if baseline_total is not None and candidate_total is not None:
                if candidate_total < baseline_total:
                    status = "PARTIALLY_PASSED"

        evidence = {
            "classification": "candidate_test_execution",
            "baseline_status": baseline.status,
            "mutant_status": mutant_result.status,
            "baseline_failure_ids": baseline_failure_ids,
            "mutant_failure_ids": mutant_failure_ids,
            "candidate_failure_ids": candidate_failure_ids,
            "new_candidate_failure_ids": sorted(
                set(candidate_failure_ids) - set(baseline_failure_ids)
            ),
            "diagnosed_test": _safe_test_identifier(diagnosed_test) if diagnosed_test else None,
            "diagnosed_test_state": diagnosed_state,
            "candidate_output_truncated": output_truncated,
            "original_source_sha256": candidate.original_source_sha256,
            "proposed_source_sha256": candidate.proposed_source_sha256,
            "repair_candidate_confidence": candidate.confidence_score,
            "behavioral_correctness_proven": False,
        }
        error_code = run.infrastructure_error
        if status == "TIMEOUT":
            error_code = "TEST_EXECUTION_TIMEOUT"
        elif status == "ERROR" and error_code is None:
            error_code = "TEST_RUNNER_ERROR"
        return status, error_code, run, evidence

    @staticmethod
    def _validate_candidate_metadata(
        candidate: RepairCandidate,
        report: FailureReport,
    ) -> None:
        if not candidate.target_file or not candidate.patch_content:
            raise EvaluationRejected("PATCH_METADATA_MISSING")
        if report.mutation_record_id != candidate.mutation_record_id:
            raise EvaluationRejected("MUTATION_DIAGNOSIS_MISMATCH")
        if report.category != _SUPPORTED_DIAGNOSIS:
            raise EvaluationRejected("UNSUPPORTED_DIAGNOSIS")
        mutation = candidate.mutation_record
        if not mutation:
            raise EvaluationRejected("MUTATION_METADATA_MISSING")
        if (
            mutation.target_file != candidate.target_file
            or mutation.mutated_code != candidate.original_expression
            or mutation.original_code != candidate.replacement_expression
            or mutation.status != "applied"
            or report.mutation_file != mutation.target_file
            or report.original_expression != mutation.original_code
            or report.mutated_expression != mutation.mutated_code
        ):
            raise EvaluationRejected("MUTATION_CANDIDATE_MISMATCH")

    @staticmethod
    def _resolve_target(workspace: Path, raw_path: str) -> Path:
        if not raw_path or "\x00" in raw_path:
            raise EvaluationRejected("UNSAFE_PATCH_PATH")
        normalized = raw_path.replace("\\", "/")
        relative = PurePosixPath(normalized)
        if (
            relative.is_absolute()
            or PureWindowsPath(raw_path).is_absolute()
            or PureWindowsPath(raw_path).drive
            or any(part in {"", ".", ".."} for part in relative.parts)
            or relative.suffix.casefold() != ".py"
        ):
            raise EvaluationRejected("UNSAFE_PATCH_PATH")
        root = workspace.resolve()
        target = root.joinpath(*relative.parts)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise EvaluationRejected("SYMLINK_PATCH_PATH")
        try:
            resolved = target.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            raise EvaluationRejected("PATCH_TARGET_MISSING") from None
        if not resolved.is_file():
            raise EvaluationRejected("PATCH_TARGET_MISSING")
        return resolved

    @staticmethod
    def _read_normalized_source(path: Path) -> str:
        try:
            return path.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            raise EvaluationRejected("PATCH_TARGET_NOT_UTF8") from None

    @staticmethod
    def _verify_ast_target(
        tree: ast.AST,
        mutation: MutationRecord,
        candidate: RepairCandidate,
    ) -> None:
        matches = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.expr)
            and getattr(node, "lineno", None) == mutation.line_number
            and getattr(node, "col_offset", None) == mutation.col_offset
            and ast.unparse(node) == candidate.original_expression
        ]
        if len(matches) != 1:
            raise EvaluationRejected("AST_TARGET_AMBIGUOUS" if matches else "AST_TARGET_NOT_FOUND")

    @staticmethod
    def _classify_run(
        status: str,
        timed_out: bool,
        infrastructure_error: str | None,
    ) -> RepairEvaluationStatus:
        if timed_out or status == "timeout":
            return "TIMEOUT"
        if status == "error" or infrastructure_error:
            return "ERROR"
        if status == "passed":
            return "PASSED"
        return "FAILED"

    @staticmethod
    def _complete(db: Session, evaluation: RepairEvaluation) -> None:
        evaluation.completed_at = datetime.now(UTC)
        db.add(evaluation)
        db.commit()
        db.refresh(evaluation)


def _apply_unified_patch(patch: str, source: str, target_file: str) -> str:
    try:
        patch_size = len(patch.encode("utf-8"))
    except UnicodeEncodeError:
        raise EvaluationRejected("PATCH_ENCODING_INVALID") from None
    if patch_size > 1024 * 1024:
        raise EvaluationRejected("PATCH_TOO_LARGE")
    patch_lines = patch.splitlines()
    if len(patch_lines) < 3:
        raise EvaluationRejected("PATCH_MALFORMED")
    if patch_lines[0] != f"--- a/{target_file}" or patch_lines[1] != f"+++ b/{target_file}":
        raise EvaluationRejected("PATCH_PATH_MISMATCH")

    original_lines = source.splitlines()
    output_lines: list[str] = []
    source_cursor = 0
    patch_cursor = 2
    changed = False
    hunk_count = 0
    while patch_cursor < len(patch_lines):
        match = _HUNK_HEADER.fullmatch(patch_lines[patch_cursor])
        if not match:
            raise EvaluationRejected("PATCH_MALFORMED")
        old_start = int(match.group(1))
        old_count = int(match.group(2) or 1)
        new_start = int(match.group(3))
        new_count = int(match.group(4) or 1)
        if old_count == 0 or old_start < 1:
            raise EvaluationRejected("PATCH_HUNK_UNSUPPORTED")
        old_index = old_start - 1
        if old_index < source_cursor or old_index > len(original_lines):
            raise EvaluationRejected("PATCH_HUNK_OUT_OF_RANGE")
        output_lines.extend(original_lines[source_cursor:old_index])
        source_cursor = old_index
        if new_start - 1 != len(output_lines):
            raise EvaluationRejected("PATCH_HUNK_OUT_OF_RANGE")
        patch_cursor += 1
        observed_old = 0
        observed_new = 0
        hunk_changed = False
        while patch_cursor < len(patch_lines) and not patch_lines[patch_cursor].startswith("@@ "):
            line = patch_lines[patch_cursor]
            if line == r"\ No newline at end of file" or not line:
                raise EvaluationRejected("PATCH_MALFORMED")
            prefix, content = line[0], line[1:]
            if prefix in {" ", "-"}:
                if source_cursor >= len(original_lines) or original_lines[source_cursor] != content:
                    raise EvaluationRejected("PATCH_CONTEXT_MISMATCH")
                source_cursor += 1
                observed_old += 1
            if prefix in {" ", "+"}:
                output_lines.append(content)
                observed_new += 1
            if prefix == "-":
                hunk_changed = True
            elif prefix == "+":
                hunk_changed = True
            elif prefix != " ":
                raise EvaluationRejected("PATCH_MALFORMED")
            patch_cursor += 1
        if observed_old != old_count or observed_new != new_count or not hunk_changed:
            raise EvaluationRejected("PATCH_HUNK_COUNT_MISMATCH")
        changed = True
        hunk_count += 1

    if not changed or hunk_count == 0:
        raise EvaluationRejected("PATCH_EMPTY")
    output_lines.extend(original_lines[source_cursor:])
    proposed = "\n".join(output_lines)
    if source.endswith("\n"):
        proposed += "\n"
    return proposed


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_test_identifier(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.replace("\\", "/")
    if normalized.startswith("/workspace/"):
        normalized = normalized[len("/workspace/") :]
    elif normalized.startswith("workspace/"):
        normalized = normalized[len("workspace/") :]
    return normalized


def _failure_ids(parsed: ParsedTestOutput) -> list[str]:
    identifiers = sorted(
        {_safe_test_identifier(item.test_identifier) for item in parsed.failures} - {""}
    )
    return identifiers[:_MAX_FAILURE_IDS]


def _matches_test_id(expected: str, candidates: list[str]) -> bool:
    return any(expected == candidate for candidate in candidates)


def _test_total(
    passed: int | None,
    failed: int | None,
    skipped: int | None,
) -> int | None:
    values = (passed, failed, skipped)
    if all(value is None for value in values):
        return None
    return sum(value or 0 for value in values)


repair_evaluation_service = RepairEvaluationService()
