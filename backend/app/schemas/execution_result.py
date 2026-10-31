import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class ExecutionResultBase(BaseModel):
    status: str = Field(default="pending", max_length=50)
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    duration_ms: Optional[int] = None
    test_output: Optional[Dict[str, Any]] = None


class ExecutionResultCreate(ExecutionResultBase):
    mutation_record_id: uuid.UUID


class ExecutionResultResponse(ExecutionResultBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mutation_record_id: uuid.UUID
    created_at: datetime
