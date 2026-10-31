import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FailureReportBase(BaseModel):
    title: str = Field(..., max_length=255)
    failure_type: str = Field(..., max_length=100)
    root_cause_analysis: str | None = None
    suggested_repair: str | None = None
    severity: str = Field(default="medium", max_length=50)
    status: str = Field(default="open", max_length=50)


class FailureReportCreate(FailureReportBase):
    analysis_run_id: uuid.UUID
    execution_result_id: uuid.UUID | None = None


class FailureReportResponse(FailureReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    execution_result_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
