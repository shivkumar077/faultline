from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def get_health() -> HealthResponse:
    """Return application health status and basic service metadata."""
    return HealthResponse(
        status="healthy",
        service=settings.APP_NAME.lower() + "-api",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
