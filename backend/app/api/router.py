from fastapi import APIRouter

from app.api.characters import router as characters_router
from app.api.composition import router as composition_router
from app.api.generation import router as generation_router
from app.api.projects import router as projects_router
from app.api.scenes import router as scenes_router

api_router = APIRouter(prefix="/api")
api_router.include_router(projects_router)
api_router.include_router(scenes_router)
api_router.include_router(characters_router)
api_router.include_router(generation_router)
api_router.include_router(composition_router)
