import logging

from fastapi import APIRouter, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.logging_config import safe_error_log
from app.db.session import engine
from app.schemas.common import HealthResponse, ReadinessResponse
from app.services.sandbox.docker_runtime import docker_runtime

logger = logging.getLogger("faultline.health")
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
@router.get("/health/live", response_model=HealthResponse, tags=["Health"])
def get_health() -> HealthResponse:
    """Return liveness status without depending on external services."""
    return HealthResponse(
        status="healthy",
        service=settings.APP_NAME.lower() + "-api",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )


@router.get("/health/ready", response_model=ReadinessResponse, tags=["Health"])
def get_readiness(response: Response) -> ReadinessResponse:
    """Check database readiness and report isolated runner availability."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_status = "available"
    except SQLAlchemyError as exc:
        safe_error_log(logger, "database_readiness_failed", exc)
        database_status = "unavailable"

    runner_status = "available" if docker_runtime.check_availability() else "unavailable"
    if database_status == "unavailable":
        status = "not_ready"
        response.status_code = 503
    elif runner_status == "unavailable":
        status = "degraded"
    else:
        status = "ready"

    return ReadinessResponse(
        status=status,
        service=settings.APP_NAME.lower() + "-api",
        database=database_status,
        execution_runner=runner_status,
    )
