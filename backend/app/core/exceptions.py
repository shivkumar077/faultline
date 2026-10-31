from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class FaultlineException(HTTPException):
    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str = "FAULTLINE_ERROR",
        headers: Optional[Dict[str, str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code
        self.extra = extra or {}


class NotFoundException(FaultlineException):
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} '{identifier}' not found.",
            error_code=f"{resource.upper()}_NOT_FOUND",
        )


class DuplicateResourceException(FaultlineException):
    def __init__(self, resource: str, field: str, value: Any):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{resource} with {field} '{value}' already exists.",
            error_code=f"{resource.upper()}_ALREADY_EXISTS",
        )


class ValidationException(FaultlineException):
    def __init__(self, detail: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            error_code="VALIDATION_ERROR",
            extra=extra,
        )


class DatabaseException(FaultlineException):
    def __init__(self, detail: str = "Database operation failed"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="DATABASE_ERROR",
        )
