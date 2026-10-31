import uuid
from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

RepairEvaluationStatus = Literal[
    "RUNNING",
    "PASSED",
    "PARTIALLY_PASSED",
    "FAILED",
    "TIMEOUT",
    "ERROR",
    "INVALID",
]
ForgeFitStatus = Literal[
    "not_requested",
    "not_configured",
    "running",
    "completed",
    "interrupted",
    "failed",
    "error",
]


class ForgeFitScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_url: AnyHttpUrl
    request_count: int = Field(default=10, ge=1, le=1000)
    timeout_seconds: float = Field(default=5.0, gt=0, le=120)
    artificial_latency_ms: int = Field(default=0, ge=0, le=60_000)
    failure_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    total_deadline_seconds: float = Field(default=30.0, gt=0, le=3600)
    allow_external: bool = False
    authorized_acknowledgement: bool = False
    seed: int | None = None


class RepairEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    forgefit_scenario: ForgeFitScenarioRequest | None = None


class RepairEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repair_candidate_id: uuid.UUID
    analysis_run_id: uuid.UUID
    failure_report_id: uuid.UUID
    baseline_execution_id: uuid.UUID | None
    mutant_execution_result_id: uuid.UUID | None
    status: RepairEvaluationStatus
    error_code: str | None
    exit_code: int | None
    duration_ms: int | None
    passed_count: int | None
    failed_count: int | None
    skipped_count: int | None
    evidence: dict[str, object]
    forgefit_status: ForgeFitStatus
    forgefit_run_id: str | None
    forgefit_result: dict[str, object] | None
    forgefit_error_code: str | None
    created_at: datetime
    completed_at: datetime | None
