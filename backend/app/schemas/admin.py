from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import TaskStatus


class AdminConfigItem(BaseModel):
    key: str
    value: str | int | bool | None
    group: str


class AdminConfigResponse(BaseModel):
    items: list[AdminConfigItem]
    reloaded_at: datetime | None = None


class AdminHealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    database: Literal["ok", "error"]
    storage: Literal["ok", "error"]
    analysis_mode: str
    model_configured: bool


class AdminTaskSummary(BaseModel):
    id: UUID
    user_display_name: str
    task_status: TaskStatus
    current_step: str | None
    error_code: str | None
    error_message: str | None
    last_log_type: str | None
    last_log_content: str | None
    created_at: datetime
    finished_at: datetime | None
