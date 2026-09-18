from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentAdmin, DatabaseSession
from app.core.config import Settings, get_settings
from app.core.redaction import redact_sensitive_text
from app.core.storage import check_storage
from app.db.session import engine
from app.models.analysis import AnalysisTask
from app.schemas.admin import (
    AdminConfigItem,
    AdminConfigResponse,
    AdminHealthResponse,
    AdminTaskSummary,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _public_config(settings: Settings) -> list[AdminConfigItem]:
    values = (
        ("app_name", settings.app_name, "application"),
        ("app_env", settings.app_env, "application"),
        ("analysis_mode", settings.analysis_mode, "analysis"),
        ("openai_model", settings.openai_model, "analysis"),
        ("websocket_token_ttl_seconds", settings.websocket_token_ttl_seconds, "security"),
        ("attachment_max_file_bytes", settings.attachment_max_file_bytes, "attachment"),
        (
            "attachment_max_conversation_bytes",
            settings.attachment_max_conversation_bytes,
            "attachment",
        ),
        ("sql_statement_timeout_ms", settings.sql_statement_timeout_ms, "query"),
        ("sql_max_rows", settings.sql_max_rows, "query"),
    )
    return [AdminConfigItem(key=key, value=value, group=group) for key, value, group in values]


@router.get("/configs", response_model=AdminConfigResponse)
async def list_configs(_: CurrentAdmin) -> AdminConfigResponse:
    return AdminConfigResponse(items=_public_config(get_settings()))


@router.post("/reload", response_model=AdminConfigResponse)
async def reload_configs(_: CurrentAdmin) -> AdminConfigResponse:
    get_settings.cache_clear()
    settings = get_settings()
    return AdminConfigResponse(
        items=_public_config(settings),
        reloaded_at=datetime.now(UTC),
    )


@router.get("/health", response_model=AdminHealthResponse)
async def admin_health(_: CurrentAdmin) -> AdminHealthResponse:
    settings = get_settings()
    database_status = "ok"
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"
    storage_ok, _ = check_storage(settings.storage_path)
    storage_status = "ok" if storage_ok else "error"
    return AdminHealthResponse(
        status="healthy" if database_status == storage_status == "ok" else "degraded",
        database=database_status,
        storage=storage_status,
        analysis_mode=settings.analysis_mode,
        model_configured=bool(settings.openai_api_key and settings.openai_model),
    )


@router.get("/tasks", response_model=list[AdminTaskSummary])
async def list_recent_tasks(
    session: DatabaseSession,
    _: CurrentAdmin,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[AdminTaskSummary]:
    tasks = list(
        await session.scalars(
            select(AnalysisTask)
            .options(selectinload(AnalysisTask.user), selectinload(AnalysisTask.logs))
            .order_by(AnalysisTask.created_at.desc())
            .limit(limit)
        )
    )
    summaries: list[AdminTaskSummary] = []
    for task in tasks:
        last_log = task.logs[-1] if task.logs else None
        summaries.append(
            AdminTaskSummary(
                id=task.id,
                user_display_name=task.user.display_name,
                task_status=task.task_status,
                current_step=task.current_step,
                error_code=task.error_code,
                error_message=(
                    redact_sensitive_text(task.error_message) if task.error_message else None
                ),
                last_log_type=last_log.log_type if last_log else None,
                last_log_content=(
                    redact_sensitive_text(last_log.log_content) if last_log else None
                ),
                created_at=task.created_at,
                finished_at=task.finished_at,
            )
        )
    return summaries
