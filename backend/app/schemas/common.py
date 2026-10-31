from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class MessageResponse(BaseModel):
    message: str


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number starting from 1")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page (max 100)")


class PaginatedResponse[T](BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
