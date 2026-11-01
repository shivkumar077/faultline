import re
import unicodedata
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_GIT_REF_FORBIDDEN = re.compile(r"[\x00-\x20\x7f~^:?*\\\[]")


def _validate_branch(value: str) -> str:
    branch = value.strip() or "main"
    segments = branch.split("/")
    if (
        branch.startswith("-")
        or branch.startswith("/")
        or branch.endswith(("/", ".", ".lock"))
        or ".." in branch
        or "@{" in branch
        or branch == "@"
        or "//" in branch
        or _GIT_REF_FORBIDDEN.search(branch)
        or any(segment.startswith(".") or segment.endswith(".lock") for segment in segments)
        or any(unicodedata.category(character) == "Cc" for character in branch)
    ):
        raise ValueError("Branch must be a valid Git branch name.")
    return branch


class RepositoryRegistrationRequest(BaseModel):
    repository_url: str = Field(
        ..., max_length=512, description="Public GitHub repository HTTPS URL"
    )
    branch: str = Field(default="main", max_length=255, description="Target branch to inspect")

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        return _validate_branch(value)


class RepositoryConnectionBase(BaseModel):
    provider: str = Field(default="github", max_length=50)
    repository_url: str = Field(..., max_length=512)
    branch: str = Field(default="main", max_length=255)
    auth_type: str = Field(default="none", max_length=50)
    status: str = Field(default="connected", max_length=50)

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        return _validate_branch(value)


class RepositoryConnectionCreate(RepositoryConnectionBase):
    project_id: uuid.UUID


class RepositoryConnectionResponse(RepositoryConnectionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
