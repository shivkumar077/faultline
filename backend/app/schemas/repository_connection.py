import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepositoryConnectionBase(BaseModel):
    provider: str = Field(default="github", max_length=50)
    repository_url: str = Field(..., max_length=512)
    branch: str = Field(default="main", max_length=255)
    auth_type: str = Field(default="none", max_length=50)
    status: str = Field(default="connected", max_length=50)


class RepositoryConnectionCreate(RepositoryConnectionBase):
    project_id: uuid.UUID


class RepositoryConnectionResponse(RepositoryConnectionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
