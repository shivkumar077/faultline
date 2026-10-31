import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.failure_report import FailureReportResponse

DiagnosisCategory = Literal[
    "baseline_failure",
    "introduced_failure",
    "existing_baseline_failure",
    "failure_changed",
    "passed_both",
    "timeout",
    "infrastructure_error",
    "execution_error",
    "invalid_mutation",
    "failure_details_unavailable",
]


class DiagnoseAnalysisRequest(BaseModel):
    execution_ids: list[uuid.UUID] | None = Field(
        default=None,
        max_length=1000,
        description="Mutant execution IDs to diagnose; omitted means all results for the analysis.",
    )


class DiagnosisSummary(BaseModel):
    baseline_failures: int = 0
    introduced_failures: int = 0
    existing_failures: int = 0
    changed_failures: int = 0
    passed_both_tests_observed: int = 0
    failure_details_unavailable: int = 0
    timed_out: int = 0
    infrastructure_errors: int = 0
    execution_errors: int = 0
    invalid_mutations: int = 0
    passing_runs_without_shared_test_ids: int = 0


class TestComparison(BaseModel):
    execution_result_id: uuid.UUID | None = None
    mutation_record_id: uuid.UUID | None = None
    test_identifier: str | None = None
    category: DiagnosisCategory
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    explanation: str


class DiagnosisRunResponse(BaseModel):
    analysis_run_id: uuid.UUID
    baseline_execution_id: uuid.UUID
    summary: DiagnosisSummary
    comparisons: list[TestComparison]
    reports: list[FailureReportResponse]
