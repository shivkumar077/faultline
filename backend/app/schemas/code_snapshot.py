import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CodeSnapshotBase(BaseModel):
    commit_hash: str = Field(..., max_length=64)
    branch: str = Field(default="main", max_length=255)
    file_tree_summary: dict[str, Any] | None = None
    status: str = Field(default="captured", max_length=50)


class CodeSnapshotCreate(CodeSnapshotBase):
    project_id: uuid.UUID
    repository_connection_id: uuid.UUID | None = None


class CodeSnapshotResponse(CodeSnapshotBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    repository_connection_id: uuid.UUID | None = None
    created_at: datetime
