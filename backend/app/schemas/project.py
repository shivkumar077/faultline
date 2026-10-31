import re
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: Optional[str] = Field(None, description="Detailed project description")
    status: str = Field(default="active", max_length=50, description="Project status")


class ProjectCreate(ProjectBase):
    slug: Optional[str] = Field(
        None, max_length=255, description="Unique slug for the project. Auto-generated if omitted."
    )

    @field_validator("slug", mode="before")
    @classmethod
    def validate_or_generate_slug(cls, v: Optional[str], info) -> Optional[str]:
        if v and v.strip():
            return slugify(v)
        # If slug is not provided, slugify name if present in data
        name = info.data.get("name") if hasattr(info, "data") else None
        if name:
            return slugify(name)
        return v


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(None, max_length=50)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return slugify(v)
        return v


class ProjectResponse(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    created_at: datetime
    updated_at: datetime


class ProjectDetailResponse(ProjectResponse):
    model_config = ConfigDict(from_attributes=True)

    repository_connections_count: int = 0
    code_snapshots_count: int = 0
    analysis_runs_count: int = 0
