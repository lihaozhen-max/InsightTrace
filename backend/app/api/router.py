from fastapi import APIRouter

from app.api.routes.attachments import router as attachments_router
from app.api.routes.auth import router as auth_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.api.routes.realtime import router as realtime_router
from app.api.routes.results import router as results_router
from app.api.routes.tasks import router as tasks_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(attachments_router)
api_router.include_router(conversations_router)
api_router.include_router(tasks_router)
api_router.include_router(realtime_router)
api_router.include_router(results_router)
api_router.include_router(health_router)
