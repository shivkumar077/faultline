import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MutationRecordBase(BaseModel):
    mutation_type: str = Field(..., max_length=100)
    target_file: str = Field(..., max_length=1024)
    line_number: int = Field(..., ge=1)
    original_code: str
    mutated_code: str
    status: str = Field(default="applied", max_length=50)


class MutationRecordCreate(MutationRecordBase):
    analysis_run_id: uuid.UUID


class MutationRecordResponse(MutationRecordBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    created_at: datetime
