import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionResultBase(BaseModel):
    status: str = Field(default="pending", max_length=50)
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    duration_ms: int | None = None
    test_output: dict[str, Any] | None = None


class ExecutionResultCreate(ExecutionResultBase):
    mutation_record_id: uuid.UUID


class ExecutionResultResponse(ExecutionResultBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mutation_record_id: uuid.UUID
    created_at: datetime
