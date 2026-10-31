"""Compare persisted baseline and mutant output and persist evidence-backed reports."""

import hashlib
import logging
import uuid
from collections import Counter
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import FaultlineException, NotFoundException
from app.models.baseline_execution import BaselineExecution
from app.models.execution_result import ExecutionResult
from app.models.failure_report import FailureReport
from app.models.mutation_record import MutationRecord
from app.repositories.analysis_repository import analysis_repository
from app.repositories.baseline_execution_repository import baseline_execution_repository
from app.repositories.execution_result_repository import execution_result_repository
from app.repositories.failure_report_repository import (
    FailureReportRepository,
    failure_report_repository,
)
from app.schemas.common import PaginatedResponse
from app.schemas.diagnosis import (
    DiagnosisRunResponse,
    DiagnosisSummary,
    TestComparison,
)
from app.schemas.failure_report import FailureReportResponse
from app.services.diagnosis_parser import (
    ParsedFailure,
    ParsedTestOutput,
    TracebackFrame,
    parse_failure_output,
)

logger = logging.getLogger("faultline.diagnosis")


class FailureDiagnosisService:
    def __init__(
        self,
        *,
        reports: FailureReportRepository | None = None,
    ):
        self.analysis_repo = analysis_repository
        self.baseline_repo = baseline_execution_repository
        self.result_repo = execution_result_repository
        self.report_repo = reports or failure_report_repository

    def diagnose_analysis(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        *,
        execution_ids: list[uuid.UUID] | None = None,
    ) -> DiagnosisRunResponse:
        analysis = self.analysis_repo.get(db, analysis_id)
        if not analysis:
            raise NotFoundException("AnalysisRun", analysis_id)
        if analysis.status == "running":
            raise FaultlineException(
                status_code=409,
                detail="Diagnosis is unavailable while execution is running.",
                error_code="EXECUTION_IN_PROGRESS",
            )

        baseline = self.baseline_repo.get_by_analysis(db, analysis_id)
        if not baseline:
            raise FaultlineException(
                status_code=409,
                detail="A persisted baseline execution is required before diagnosis.",
                error_code="BASELINE_EXECUTION_REQUIRED",
            )
        if baseline.status in {"pending", "running"}:
            raise FaultlineException(
                status_code=409,
                detail="Diagnosis is unavailable until baseline execution completes.",
                error_code="EXECUTION_IN_PROGRESS",
            )

        all_results = list(self.result_repo.get_by_analysis(db, analysis_id))
        if execution_ids is None:
            results = all_results
        else:
            results_by_id = {result.id: result for result in all_results}
            missing = set(execution_ids) - results_by_id.keys()
            if missing:
                raise FaultlineException(
                    status_code=422,
                    detail="One or more execution IDs do not belong to this analysis.",
                    error_code="INVALID_EXECUTION_IDS",
                )
            selected = set(execution_ids)
            results = [result for result in all_results if result.id in selected]
        if any(result.status.lower() in {"pending", "running"} for result in results):
            raise FaultlineException(
                status_code=409,
                detail="Diagnosis is unavailable until selected mutant executions complete.",
                error_code="EXECUTION_IN_PROGRESS",
            )

        baseline_output = parse_failure_output(
            baseline.stdout,
            baseline.stderr,
            baseline.framework,
        )
        drafts: list[dict[str, Any]] = []
        comparisons: list[TestComparison] = []
        counters: Counter[str] = Counter()
        baseline_failures = self._baseline_failures(
            analysis_id,
            baseline,
            baseline_output,
            drafts,
            comparisons,
            counters,
        )

        for result in results:
            mutation = result.mutation_record
            if result.status == "SURVIVED" and result.mutation_application_status == "applied":
                self._record_success_comparisons(
                    baseline,
                    result,
                    mutation,
                    baseline_output,
                    comparisons,
                    counters,
                )
                continue
            if result.status == "KILLED" and result.mutation_application_status == "applied":
                self._diagnose_killed_result(
                    analysis_id,
                    baseline,
                    result,
                    mutation,
                    baseline_failures,
                    drafts,
                    comparisons,
                    counters,
                )
                continue

            category, title, explanation, confidence, attribution = self._execution_category(result)
            counters[category] += 1
            evidence = [
                self._evidence(
                    "mutant_execution",
                    f"Persisted mutant execution status: {result.status}.",
                    "ExecutionResult.status",
                )
            ]
            if result.timed_out:
                evidence.append(
                    self._evidence("timeout", "The runner recorded a timeout.", "timed_out")
                )
            if result.infrastructure_error:
                evidence.append(
                    self._evidence(
                        "infrastructure_error",
                        f"Runner infrastructure error: {result.infrastructure_error}.",
                        "infrastructure_error",
                    )
                )
            execution_output = parse_failure_output(
                result.stdout,
                result.stderr,
                baseline.framework,
            )
            failure = execution_output.failures[0] if execution_output.failures else None
            if failure:
                evidence.extend(self._failure_evidence(failure, "mutant"))
            report = self._report_draft(
                analysis_id=analysis_id,
                execution_result=result,
                mutation=mutation,
                category=category,
                title=title,
                failure=failure,
                confidence=confidence,
                attribution=attribution,
                explanation=explanation,
                evidence=evidence,
                suggested_repair=self._guidance(category),
            )
            drafts.append(report)
            comparisons.append(
                TestComparison(
                    execution_result_id=result.id,
                    mutation_record_id=mutation.id if mutation else None,
                    test_identifier=failure.test_identifier if failure else None,
                    category=category,
                    confidence_score=confidence,
                    explanation=explanation,
                )
            )

        stored_reports = self._persist_reports(db, drafts)
        return DiagnosisRunResponse(
            analysis_run_id=analysis_id,
            baseline_execution_id=baseline.id,
            summary=DiagnosisSummary(
                baseline_failures=counters["baseline_failure"],
                introduced_failures=counters["introduced_failure"],
                existing_failures=counters["existing_baseline_failure"],
                changed_failures=counters["failure_changed"],
                passed_both_tests_observed=counters["passed_both"],
                failure_details_unavailable=counters["failure_details_unavailable"],
                timed_out=counters["timeout"],
                infrastructure_errors=counters["infrastructure_error"],
                execution_errors=counters["execution_error"],
                invalid_mutations=counters["invalid_mutation"],
                passing_runs_without_shared_test_ids=counters[
                    "passing_run_without_shared_test_ids"
                ],
            ),
            comparisons=comparisons,
            reports=[FailureReportResponse.model_validate(report) for report in stored_reports],
        )

    def list_analysis_reports(
        self,
        db: Session,
        analysis_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[FailureReportResponse]:
        if not self.analysis_repo.get(db, analysis_id):
            raise NotFoundException("AnalysisRun", analysis_id)
        reports, total = self.report_repo.get_for_analysis(
            db,
            analysis_id,
            skip=(page - 1) * page_size,
            limit=page_size,
        )
        total_pages = (total + page_size - 1) // page_size if total else 1
        return PaginatedResponse[FailureReportResponse](
            items=[FailureReportResponse.model_validate(report) for report in reports],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def get_report(self, db: Session, report_id: uuid.UUID) -> FailureReportResponse:
        report = self.report_repo.get(db, report_id)
        if not report:
            raise NotFoundException("FailureReport", report_id)
        return FailureReportResponse.model_validate(report)

    def _baseline_failures(
        self,
        analysis_id: uuid.UUID,
        baseline: BaselineExecution,
        parsed: ParsedTestOutput,
        drafts: list[dict[str, Any]],
        comparisons: list[TestComparison],
        counters: Counter[str],
    ) -> dict[str, ParsedFailure]:
        if baseline.status == "failed":
            failures = list(parsed.failures) or [ParsedFailure()]
            mapped: dict[str, ParsedFailure] = {}
            for failure in failures:
                if failure.test_identifier:
                    mapped[failure.test_identifier] = failure
                confidence = 0.95 if failure.test_identifier else 0.55
                explanation = (
                    "This failure was observed in the unmodified baseline. It is pre-existing "
                    "and must not be attributed to a mutant."
                )
                evidence = [
                    self._evidence(
                        "baseline_failure",
                        "The unmodified baseline execution is classified as failed.",
                        "BaselineExecution.status",
                    )
                ]
                evidence.extend(self._failure_evidence(failure, "baseline"))
                drafts.append(
                    self._report_draft(
                        analysis_id=analysis_id,
                        baseline_execution=baseline,
                        category="baseline_failure",
                        title=self._title("Baseline test failure", failure),
                        failure=failure,
                        confidence=confidence,
                        attribution="not_attributed",
                        explanation=explanation,
                        evidence=evidence,
                        suggested_repair=self._guidance("baseline_failure"),
                    )
                )
                comparisons.append(
                    TestComparison(
                        test_identifier=failure.test_identifier,
                        category="baseline_failure",
                        confidence_score=confidence,
                        explanation=explanation,
                    )
                )
                counters["baseline_failure"] += 1
            return mapped

        if baseline.timed_out or baseline.status == "timeout":
            category = "timeout"
            title = "Baseline test execution timed out"
            explanation = "The baseline test run did not complete within its execution limit."
            confidence = 0.95
        elif baseline.status == "error":
            category = (
                "infrastructure_error" if baseline.infrastructure_error else "execution_error"
            )
            title = "Baseline execution could not be completed"
            explanation = (
                "The baseline did not provide a valid comparison point; mutant failures cannot "
                "be attributed against it."
            )
            confidence = 0.95 if baseline.infrastructure_error else 0.8
        else:
            return {}

        counters[category] += 1
        failure = parsed.failures[0] if parsed.failures else None
        evidence = [
            self._evidence(
                "baseline_execution",
                f"Persisted baseline execution status: {baseline.status}.",
                "BaselineExecution.status",
            )
        ]
        if failure:
            evidence.extend(self._failure_evidence(failure, "baseline"))
        drafts.append(
            self._report_draft(
                analysis_id=analysis_id,
                baseline_execution=baseline,
                category=category,
                title=title,
                failure=failure,
                confidence=confidence,
                attribution="unknown",
                explanation=explanation,
                evidence=evidence,
                suggested_repair=self._guidance(category),
            )
        )
        comparisons.append(
            TestComparison(
                test_identifier=failure.test_identifier if failure else None,
                category=category,
                confidence_score=confidence,
                explanation=explanation,
            )
        )
        return {}

    def _diagnose_killed_result(
        self,
        analysis_id: uuid.UUID,
        baseline: BaselineExecution,
        result: ExecutionResult,
        mutation: MutationRecord | None,
        baseline_failures: dict[str, ParsedFailure],
        drafts: list[dict[str, Any]],
        comparisons: list[TestComparison],
        counters: Counter[str],
    ) -> None:
        parsed = parse_failure_output(result.stdout, result.stderr, baseline.framework)
        failures = list(parsed.failures) or [ParsedFailure()]
        for failure in failures:
            prior = baseline_failures.get(failure.test_identifier or "")
            same_failure = bool(prior and _failure_signature(prior) == _failure_signature(failure))
            if prior and same_failure:
                category = "existing_baseline_failure"
                attribution = "not_attributed"
                explanation = (
                    "The same test and failure signature were observed in the unmodified "
                    "baseline. This failure is pre-existing and is not attributed to the mutation."
                )
                confidence = 0.98
            elif prior:
                category = "failure_changed"
                attribution = "inferred"
                explanation = (
                    "The test already failed in the baseline, but the mutant produced a different "
                    "failure signature. The mutation may have changed the symptom; "
                    "the pre-existing "
                    "failure prevents a claim that it introduced the failure."
                )
                confidence = self._confidence(category, failure, mutation)
            elif baseline.status == "passed":
                category = "introduced_failure"
                attribution = "inferred"
                explanation = (
                    "The baseline passed and this mutant execution failed. This is evidence that "
                    "the mutation is associated with a new failure, not proof "
                    "that it is the sole cause."
                )
                confidence = self._confidence(category, failure, mutation)
            else:
                category = "failure_details_unavailable"
                attribution = "unknown"
                explanation = (
                    "A valid passing baseline comparison is unavailable, so the failure cannot "
                    "be reliably attributed to this mutation."
                )
                confidence = 0.25

            counters[category] += 1
            evidence = [
                self._evidence(
                    "baseline_comparison",
                    f"Baseline status: {baseline.status}; mutant status: {result.status}.",
                    "BaselineExecution.status / ExecutionResult.status",
                    supports_cause=category == "introduced_failure",
                )
            ]
            evidence.extend(self._failure_evidence(failure, "mutant"))
            evidence.extend(self._mutation_evidence(mutation, failure))
            if prior:
                evidence.extend(self._failure_evidence(prior, "baseline"))

            mutation_expression = (
                f" Mutation {mutation.id} changed {mutation.target_file}:{mutation.line_number} "
                f"from {mutation.original_code!r} to {mutation.mutated_code!r}."
                if mutation
                else ""
            )
            root_cause = explanation + mutation_expression
            drafts.append(
                self._report_draft(
                    analysis_id=analysis_id,
                    execution_result=result,
                    mutation=mutation,
                    category=category,
                    title=self._title(category.replace("_", " ").capitalize(), failure),
                    failure=failure,
                    confidence=confidence,
                    attribution=attribution,
                    explanation=explanation,
                    evidence=evidence,
                    root_cause=root_cause,
                    suggested_repair=self._guidance(category),
                )
            )
            comparisons.append(
                TestComparison(
                    execution_result_id=result.id,
                    mutation_record_id=mutation.id if mutation else None,
                    test_identifier=failure.test_identifier,
                    category=category,
                    confidence_score=confidence,
                    explanation=explanation,
                )
            )

    @staticmethod
    def _record_success_comparisons(
        baseline: BaselineExecution,
        result: ExecutionResult,
        mutation: MutationRecord | None,
        baseline_output: ParsedTestOutput,
        comparisons: list[TestComparison],
        counters: Counter[str],
    ) -> None:
        if baseline.status != "passed":
            return
        mutant_output = parse_failure_output(result.stdout, result.stderr, baseline.framework)
        common_tests = sorted(
            set(baseline_output.passed_test_ids) & set(mutant_output.passed_test_ids)
        )
        for test_identifier in common_tests:
            counters["passed_both"] += 1
            comparisons.append(
                TestComparison(
                    execution_result_id=result.id,
                    mutation_record_id=mutation.id if mutation else None,
                    test_identifier=test_identifier,
                    category="passed_both",
                    confidence_score=1.0,
                    explanation=(
                        "The same test identifier was explicitly reported as passing in both runs."
                    ),
                )
            )
        if not common_tests:
            counters["passing_run_without_shared_test_ids"] += 1
            explanation = (
                "The baseline and mutant runs both completed successfully. Captured output "
                "did not provide matching passing test identifiers, so this is a "
                "run-level comparison."
                if not baseline_output.passed_test_ids or not mutant_output.passed_test_ids
                else "Both runs completed successfully, but no test identifier was reported as "
                "passing in both outputs; no test-level match is asserted."
            )
            comparisons.append(
                TestComparison(
                    execution_result_id=result.id,
                    mutation_record_id=mutation.id if mutation else None,
                    category="passed_both",
                    confidence_score=0.8,
                    explanation=explanation,
                )
            )

    @staticmethod
    def _execution_category(
        result: ExecutionResult,
    ) -> tuple[str, str, str, float, str]:
        if result.status == "TIMEOUT" or result.timed_out:
            return (
                "timeout",
                "Mutant execution timed out",
                "The mutant test run timed out; the timeout alone does not identify a code defect.",
                0.95,
                "unknown",
            )
        if result.status == "ERROR" and result.infrastructure_error:
            return (
                "infrastructure_error",
                "Mutant execution failed due to infrastructure",
                "The execution runner reported an infrastructure error; "
                "no test-level cause is inferred.",
                0.95,
                "unknown",
            )
        if (
            result.status == "INVALID"
            or result.mutation_application_status == "invalid"
            or (
                result.status in {"KILLED", "SURVIVED"}
                and result.mutation_application_status != "applied"
            )
        ):
            return (
                "invalid_mutation",
                "Mutation could not be applied",
                "The mutation did not validate against the source snapshot and was not executed.",
                0.98,
                "not_applicable",
            )
        return (
            "execution_error",
            "Mutant execution could not be classified",
            "The mutant did not produce a normal test result; no source-level cause is inferred.",
            0.8,
            "unknown",
        )

    @staticmethod
    def _confidence(
        category: str,
        failure: ParsedFailure,
        mutation: MutationRecord | None,
    ) -> float:
        score = 0.55 if category == "introduced_failure" else 0.45
        if failure.test_identifier:
            score += 0.1
        matching_frames = (
            [
                frame
                for frame in failure.traceback_frames
                if _same_source(frame.file_path, mutation.target_file)
            ]
            if mutation
            else []
        )
        if matching_frames:
            score += 0.15
        if mutation and any(frame.line_number == mutation.line_number for frame in matching_frames):
            score += 0.1
        if failure.exception_type or failure.failing_assertion:
            score += 0.05
        return min(round(score, 2), 0.95)

    def _report_draft(
        self,
        *,
        analysis_id: uuid.UUID,
        category: str,
        title: str,
        confidence: float,
        attribution: str,
        explanation: str,
        evidence: list[dict[str, Any]],
        suggested_repair: str,
        failure: ParsedFailure | None = None,
        baseline_execution: BaselineExecution | None = None,
        execution_result: ExecutionResult | None = None,
        mutation: MutationRecord | None = None,
        root_cause: str | None = None,
    ) -> dict[str, Any]:
        execution_id = (
            str(execution_result.id)
            if execution_result
            else str(baseline_execution.id)
            if baseline_execution
            else "unknown-execution"
        )
        failure_identity = "|".join(
            (
                failure.test_identifier or "unknown-test",
                failure.exception_type or "",
                failure.exception_message or "",
                failure.source_file or "",
                str(failure.source_line or ""),
            )
            if failure
            and any(
                (
                    failure.test_identifier,
                    failure.exception_type,
                    failure.exception_message,
                    failure.source_file,
                    failure.source_line,
                )
            )
            else ("unknown-test",)
        )
        diagnosis_key = hashlib.sha256(f"{execution_id}|{failure_identity}".encode()).hexdigest()
        affected_test = failure.test_identifier if failure else None
        return {
            "analysis_run_id": analysis_id,
            "execution_result_id": execution_result.id if execution_result else None,
            "baseline_execution_id": baseline_execution.id if baseline_execution else None,
            "mutation_record_id": mutation.id if mutation else None,
            "diagnosis_key": diagnosis_key,
            "title": title[:255],
            "failure_type": category,
            "category": category,
            "confidence_score": confidence,
            "causal_attribution": attribution,
            "affected_test": _limit_text(affected_test, 1024),
            "test_identifier": _limit_text(failure.test_identifier, 1024) if failure else None,
            "test_file": _limit_text(failure.test_file, 1024) if failure else None,
            "test_class": _limit_text(failure.test_class, 255) if failure else None,
            "test_function": _limit_text(failure.test_function, 255) if failure else None,
            "mutation_file": _limit_text(mutation.target_file, 1024) if mutation else None,
            "mutation_line": mutation.line_number if mutation else None,
            "original_expression": mutation.original_code if mutation else None,
            "mutated_expression": mutation.mutated_code if mutation else None,
            "exception_type": _limit_text(failure.exception_type, 512) if failure else None,
            "exception_message": failure.exception_message if failure else None,
            "failing_assertion": failure.failing_assertion if failure else None,
            "failure_summary": failure.summary if failure else None,
            "source_file": _limit_text(failure.source_file, 1024) if failure else None,
            "source_line": failure.source_line if failure else None,
            "source_function": _limit_text(failure.source_function, 255) if failure else None,
            "traceback_frames": (
                [self._frame_data(frame) for frame in failure.traceback_frames] if failure else None
            ),
            "evidence": evidence,
            "comparison_summary": explanation,
            "root_cause_analysis": root_cause or explanation,
            "suggested_repair": suggested_repair,
            "severity": self._severity(category),
            "status": "open",
        }

    @staticmethod
    def _frame_data(frame: TracebackFrame) -> dict[str, Any]:
        return {
            "file_path": frame.file_path,
            "line_number": frame.line_number,
            "function_name": frame.function_name,
            "source_line": frame.source_line,
        }

    @staticmethod
    def _failure_evidence(failure: ParsedFailure, execution: str) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        if failure.test_identifier:
            evidence.append(
                FailureDiagnosisService._evidence(
                    "test_identifier",
                    f"Observed failing test: {failure.test_identifier}.",
                    f"{execution} test output",
                )
            )
        if failure.exception_type:
            evidence.append(
                FailureDiagnosisService._evidence(
                    "exception",
                    f"Observed exception type: {failure.exception_type}.",
                    f"{execution} test output",
                )
            )
        if failure.exception_message:
            evidence.append(
                FailureDiagnosisService._evidence(
                    "exception_message",
                    failure.exception_message,
                    f"{execution} test output",
                )
            )
        if failure.failing_assertion:
            evidence.append(
                FailureDiagnosisService._evidence(
                    "assertion",
                    failure.failing_assertion,
                    f"{execution} test output",
                )
            )
        for frame in failure.traceback_frames:
            evidence.append(
                FailureDiagnosisService._evidence(
                    "traceback_frame",
                    f"{frame.file_path}:{frame.line_number}"
                    + (f" in {frame.function_name}" if frame.function_name else ""),
                    f"{execution} traceback",
                )
            )
        return evidence

    @staticmethod
    def _mutation_evidence(
        mutation: MutationRecord | None,
        failure: ParsedFailure,
    ) -> list[dict[str, Any]]:
        if not mutation:
            return []
        evidence = [
            FailureDiagnosisService._evidence(
                "mutation",
                f"{mutation.target_file}:{mutation.line_number} changed "
                f"{mutation.original_code!r} to {mutation.mutated_code!r}.",
                "MutationRecord",
                supports_cause=False,
            )
        ]
        matching_frames = [
            frame
            for frame in failure.traceback_frames
            if _same_source(frame.file_path, mutation.target_file)
        ]
        if matching_frames:
            evidence.append(
                FailureDiagnosisService._evidence(
                    "mutation_file_in_traceback",
                    f"A traceback frame points to the mutated file {mutation.target_file}.",
                    "TracebackFrame.file_path",
                    supports_cause=True,
                )
            )
        if any(frame.line_number == mutation.line_number for frame in matching_frames):
            evidence.append(
                FailureDiagnosisService._evidence(
                    "mutation_line_in_traceback",
                    f"A traceback frame points to the mutated line {mutation.line_number}.",
                    "TracebackFrame.line_number",
                    supports_cause=True,
                )
            )
        return evidence

    @staticmethod
    def _evidence(
        kind: str,
        detail: str,
        source: str,
        *,
        supports_cause: bool = False,
    ) -> dict[str, Any]:
        return {
            "kind": kind,
            "detail": detail,
            "source": source,
            "supports_cause": supports_cause,
        }

    @staticmethod
    def _title(prefix: str, failure: ParsedFailure) -> str:
        target = failure.test_identifier or "test details unavailable"
        suffix = f" ({failure.exception_type})" if failure.exception_type else ""
        return f"{prefix}: {target}{suffix}"

    @staticmethod
    def _guidance(category: str) -> str:
        guidance = {
            "baseline_failure": (
                "Resolve the baseline test failure before attributing later failures to a mutation."
            ),
            "introduced_failure": (
                "Review the failing assertion and mutated expression, then add or update "
                "a regression test. "
                "No code patch was generated."
            ),
            "existing_baseline_failure": (
                "Address the pre-existing baseline failure first; this report does not "
                "attribute it to the mutation."
            ),
            "failure_changed": (
                "Compare the baseline and mutant tracebacks and inspect the changed "
                "expression; the failure pre-existed."
            ),
            "failure_details_unavailable": (
                "Capture complete test output and establish a passing baseline before "
                "drawing a source-level conclusion."
            ),
            "timeout": (
                "Inspect test duration and runner limits; a timeout alone does not identify "
                "a code defect."
            ),
            "infrastructure_error": (
                "Resolve the runner or container infrastructure error and rerun execution."
            ),
            "execution_error": (
                "Inspect runner output and execution configuration, then rerun the test suite."
            ),
            "invalid_mutation": (
                "Regenerate or validate the mutation against the exact source snapshot."
            ),
        }
        return guidance.get(
            category, "Inspect the recorded execution evidence; no code patch was generated."
        )

    @staticmethod
    def _severity(category: str) -> str:
        if category in {"introduced_failure", "infrastructure_error"}:
            return "high"
        if category in {"baseline_failure", "failure_changed", "timeout", "execution_error"}:
            return "medium"
        return "low"

    def _persist_reports(
        self,
        db: Session,
        drafts: list[dict[str, Any]],
    ) -> list[FailureReport]:
        if not drafts:
            return []
        keys = [draft["diagnosis_key"] for draft in drafts]
        existing = self.report_repo.get_by_diagnosis_keys(db, keys)
        for draft in drafts:
            report = existing.get(draft["diagnosis_key"])
            if report:
                for field, value in draft.items():
                    setattr(report, field, value)
            else:
                db.add(FailureReport(**draft))
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            sqlite_conflict = (
                "unique constraint failed: failure_reports.diagnosis_key"
                in str(exc.orig).casefold()
            )
            if constraint_name != "uq_failure_reports_diagnosis_key" and not sqlite_conflict:
                raise
            concurrently_persisted = self.report_repo.get_by_diagnosis_keys(db, keys)
            if len(concurrently_persisted) != len(set(keys)):
                raise
            logger.info("Diagnosis reports already persisted by a concurrent request.")
            return [
                concurrently_persisted[key]
                for key in dict.fromkeys(keys)
                if key in concurrently_persisted
            ]
        persisted = self.report_repo.get_by_diagnosis_keys(db, keys)
        return [persisted[key] for key in dict.fromkeys(keys) if key in persisted]


def _failure_signature(failure: ParsedFailure) -> tuple[str | None, str | None, str | None]:
    return failure.exception_type, failure.exception_message, failure.failing_assertion


def _same_source(traceback_path: str, mutation_path: str) -> bool:
    traceback_path = traceback_path.replace("\\", "/").lstrip("./").casefold()
    mutation_path = mutation_path.replace("\\", "/").lstrip("./").casefold()
    return traceback_path == mutation_path or traceback_path.endswith(f"/{mutation_path}")


def _limit_text(value: str | None, limit: int) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


failure_diagnosis_service = FailureDiagnosisService()
