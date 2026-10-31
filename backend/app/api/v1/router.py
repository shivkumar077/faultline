from fastapi import APIRouter

from app.api.v1.endpoints import analyses, health, projects

api_v1_router = APIRouter()

api_v1_router.include_router(health.router)
api_v1_router.include_router(projects.router)
api_v1_router.include_router(analyses.router)
