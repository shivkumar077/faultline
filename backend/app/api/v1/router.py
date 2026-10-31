from fastapi import APIRouter

from app.api.v1.endpoints import (
    analyses,
    diagnoses,
    executions,
    health,
    projects,
    repositories,
    snapshots,
)

api_v1_router = APIRouter()

api_v1_router.include_router(health.router)
api_v1_router.include_router(projects.router)
api_v1_router.include_router(repositories.router)
api_v1_router.include_router(snapshots.router)
api_v1_router.include_router(analyses.router)
api_v1_router.include_router(executions.router)
api_v1_router.include_router(diagnoses.router)
