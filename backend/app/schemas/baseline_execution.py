"""Pydantic schemas for baseline test execution."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExecuteBaselineRequest(BaseModel):
    """Optional configuration for triggering baseline test runs."""

    timeout_seconds: int | None = Field(
        None, ge=5, le=300, description="Execution timeout override in seconds"
    )


class BaselineExecutionBase(BaseModel):
    command: str = Field(..., max_length=512)
    command_identifier: str = Field(default="pytest", max_length=50)
    framework: str = Field(default="none", max_length=50)
    test_files_count: int = 0
    status: str = Field(default="pending", max_length=50)
    exit_code: int | None = None
    passed_count: int | None = None
    failed_count: int | None = None
    skipped_count: int | None = None
    timed_out: bool = False
    infrastructure_error: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    duration_ms: int | None = None


class BaselineExecutionCreate(BaselineExecutionBase):
    analysis_run_id: uuid.UUID
    code_snapshot_id: uuid.UUID


class BaselineExecutionResponse(BaselineExecutionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    code_snapshot_id: uuid.UUID
    created_at: datetime
