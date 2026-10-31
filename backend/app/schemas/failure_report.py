import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class FailureReportBase(BaseModel):
    title: str = Field(..., max_length=255)
    failure_type: str = Field(..., max_length=100)
    root_cause_analysis: Optional[str] = None
    suggested_repair: Optional[str] = None
    severity: str = Field(default="medium", max_length=50)
    status: str = Field(default="open", max_length=50)


class FailureReportCreate(FailureReportBase):
    analysis_run_id: uuid.UUID
    execution_result_id: Optional[uuid.UUID] = None


class FailureReportResponse(FailureReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    execution_result_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
