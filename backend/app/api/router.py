from fastapi import APIRouter

from app.api.asset_hub import router as asset_hub_router
from app.api.assets import router as assets_router
from app.api.characters import router as characters_router
from app.api.composition import router as composition_router
from app.api.costs import router as costs_router
from app.api.episodes import router as episodes_router
from app.api.generation import router as generation_router
from app.api.panels import router as panels_router
from app.api.providers import router as providers_router
from app.api.projects import router as projects_router
from app.api.script_assets import router as script_assets_router
from app.api.sse import router as sse_router
from app.api.system import router as system_router
from app.api.tasks import router as tasks_router

api_router = APIRouter(prefix="/api")
api_router.include_router(projects_router)
api_router.include_router(episodes_router)
api_router.include_router(panels_router)
api_router.include_router(characters_router)
api_router.include_router(generation_router)
api_router.include_router(composition_router)
api_router.include_router(tasks_router)
api_router.include_router(costs_router)
api_router.include_router(assets_router)
api_router.include_router(asset_hub_router)
api_router.include_router(script_assets_router)
api_router.include_router(system_router)
api_router.include_router(providers_router)
api_router.include_router(sse_router)
