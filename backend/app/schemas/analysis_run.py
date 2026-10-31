import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalysisRunBase(BaseModel):
    name: str | None = Field(None, max_length=255)
    status: str = Field(default="pending", max_length=50)
    summary: dict[str, Any] | None = None


class AnalysisRunCreate(AnalysisRunBase):
    project_id: uuid.UUID
    code_snapshot_id: uuid.UUID


class AnalysisRunResponse(AnalysisRunBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    code_snapshot_id: uuid.UUID
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AnalysisRunDetailResponse(AnalysisRunResponse):
    model_config = ConfigDict(from_attributes=True)

    baseline_executions_count: int = 0
    mutation_records_count: int = 0
    failure_reports_count: int = 0
