from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings
from app.core.storage import check_storage
from app.db.session import engine

router = APIRouter(prefix="/health", tags=["health"])


class ComponentHealth(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class LiveResponse(BaseModel):
    status: Literal["alive"]
    service: str


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    service: str
    environment: str
    components: dict[str, ComponentHealth]


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    settings = get_settings()
    return LiveResponse(status="alive", service=settings.app_name)


@router.get("/ready", response_model=ReadyResponse)
async def ready(response: Response) -> ReadyResponse:
    settings = get_settings()
    components: dict[str, ComponentHealth] = {}

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        components["database"] = ComponentHealth(status="ok")
    except Exception:
        components["database"] = ComponentHealth(
            status="error",
            detail="Database connection failed",
        )

    storage_ok, storage_detail = check_storage(settings.storage_path)
    components["storage"] = ComponentHealth(
        status="ok" if storage_ok else "error",
        detail=None if storage_ok else storage_detail,
    )

    is_ready = all(component.status == "ok" for component in components.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadyResponse(
        status="ready" if is_ready else "not_ready",
        service=settings.app_name,
        environment=settings.app_env,
        components=components,
    )
