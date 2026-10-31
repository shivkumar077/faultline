"""API schemas for complete analysis execution workflows."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.baseline_execution import BaselineExecutionResponse
from app.schemas.execution_result import ExecutionResultResponse


class ExecuteAnalysisRequest(BaseModel):
    timeout_seconds: int | None = Field(default=None, ge=5, le=300)


class ExecutionRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    kind: Literal["baseline", "mutation"]
    mutation_record_id: uuid.UUID | None = None
    status: str
    exit_code: int | None = None
    duration_ms: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    timed_out: bool = False
    infrastructure_error: str | None = None


class ExecuteAnalysisResponse(BaseModel):
    analysis_run_id: uuid.UUID
    status: str
    baseline: BaselineExecutionResponse
    execution_results: list[ExecutionResultResponse]
    summary: dict[str, Any]
