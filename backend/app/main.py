import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.endpoints import health
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import FaultlineException
from app.core.logging_config import configure_logging, safe_error_log
from app.core.middleware import FaultlineSecurityMiddleware
from app.db.session import engine

configure_logging("DEBUG" if settings.DEBUG else settings.LOG_LEVEL)
logger = logging.getLogger("faultline")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown hooks."""
    logger.info(
        "Starting %s v%s in %s mode", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT
    )
    try:
        yield
    finally:
        logger.info("Shutting down %s, disposing database engine pool", settings.APP_NAME)
        engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Code-level failure engineering and remediation platform",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    FaultlineSecurityMiddleware,
    config=settings,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.TRUSTED_HOSTS,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.exception_handler(FaultlineException)
async def faultline_exception_handler(request: Request, exc: FaultlineException) -> JSONResponse:
    production = settings.ENVIRONMENT == "production"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": "The request could not be completed." if production else exc.detail,
            "error_code": exc.error_code,
            "extra": {} if production else exc.extra,
            "request_id": getattr(request.state, "request_id", uuid.uuid4().hex),
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {key: value for key, value in error.items() if key not in {"ctx", "input"}}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error in request parameters or body.",
            "error_code": "VALIDATION_ERROR",
            "extra": {"errors": errors},
            "request_id": getattr(request.state, "request_id", uuid.uuid4().hex),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": (
                "The request could not be completed."
                if settings.ENVIRONMENT == "production" and exc.status_code >= 500
                else exc.detail
            ),
            "error_code": "HTTP_ERROR",
            "extra": {},
            "request_id": getattr(request.state, "request_id", uuid.uuid4().hex),
        },
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    safe_error_log(logger, "unhandled_server_exception", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected internal server error occurred.",
            "error_code": "INTERNAL_SERVER_ERROR",
            "extra": {},
            "request_id": request_id,
        },
    )


app.include_router(health.router)
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["Root"])
def root() -> dict[str, str]:
    """Root endpoint providing service metadata and API references."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": f"{settings.API_V1_PREFIX}/docs",
        "health": "/health",
    }
