"""Pydantic schemas for baseline test execution."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExecuteBaselineRequest(BaseModel):
    """Optional configuration for triggering baseline test runs."""

    custom_command: list[str] | None = Field(
        None, description="Custom command overrides for the test runner"
    )
    timeout_seconds: int | None = Field(
        None, ge=5, le=300, description="Execution timeout override in seconds"
    )


class BaselineExecutionBase(BaseModel):
    command: str = Field(..., max_length=512)
    status: str = Field(default="pending", max_length=50)
    exit_code: int | None = None
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
