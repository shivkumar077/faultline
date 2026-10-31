import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FailureReportBase(BaseModel):
    title: str = Field(..., max_length=255)
    failure_type: str = Field(..., max_length=100)
    category: str | None = Field(default=None, max_length=50)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    causal_attribution: str | None = Field(default=None, max_length=50)
    affected_test: str | None = Field(default=None, max_length=1024)
    test_identifier: str | None = Field(default=None, max_length=1024)
    test_file: str | None = Field(default=None, max_length=1024)
    test_class: str | None = Field(default=None, max_length=255)
    test_function: str | None = Field(default=None, max_length=255)
    mutation_file: str | None = Field(default=None, max_length=1024)
    mutation_line: int | None = Field(default=None, ge=1)
    original_expression: str | None = None
    mutated_expression: str | None = None
    exception_type: str | None = Field(default=None, max_length=512)
    exception_message: str | None = None
    failing_assertion: str | None = None
    failure_summary: str | None = None
    source_file: str | None = Field(default=None, max_length=1024)
    source_line: int | None = Field(default=None, ge=1)
    source_function: str | None = Field(default=None, max_length=255)
    traceback_frames: list[dict[str, object]] | None = None
    evidence: list[dict[str, object]] | None = None
    comparison_summary: str | None = None
    root_cause_analysis: str | None = None
    suggested_repair: str | None = None
    severity: str = Field(default="medium", max_length=50)
    status: str = Field(default="open", max_length=50)


class FailureReportCreate(FailureReportBase):
    analysis_run_id: uuid.UUID
    execution_result_id: uuid.UUID | None = None
    baseline_execution_id: uuid.UUID | None = None
    mutation_record_id: uuid.UUID | None = None


class FailureReportResponse(FailureReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    execution_result_id: uuid.UUID | None = None
    baseline_execution_id: uuid.UUID | None = None
    mutation_record_id: uuid.UUID | None = None
    diagnosis_key: str | None = None
    created_at: datetime
    updated_at: datetime
