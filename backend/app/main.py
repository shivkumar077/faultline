import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints import health
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import FaultlineException
from app.db.session import engine

logger = logging.getLogger("faultline")
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


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

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Centralized exception handlers
@app.exception_handler(FaultlineException)
async def faultline_exception_handler(request: Request, exc: FaultlineException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": exc.error_code,
            "extra": exc.extra,
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error in request parameters or body.",
            "error_code": "VALIDATION_ERROR",
            "extra": {"errors": exc.errors()},
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": "HTTP_ERROR",
            "extra": {},
        },
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected internal server error occurred.",
            "error_code": "INTERNAL_SERVER_ERROR",
            "extra": {},
        },
    )


# Root health endpoint (for Docker /health container healthchecks and external monitors)
app.include_router(health.router)

# API v1 routes (/api/v1/projects, /api/v1/analyses, /api/v1/health)
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
