import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class BaselineExecutionBase(BaseModel):
    command: str = Field(..., max_length=512)
    status: str = Field(default="pending", max_length=50)
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    duration_ms: Optional[int] = None


class BaselineExecutionCreate(BaselineExecutionBase):
    analysis_run_id: uuid.UUID
    code_snapshot_id: uuid.UUID


class BaselineExecutionResponse(BaselineExecutionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    code_snapshot_id: uuid.UUID
    created_at: datetime
