from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import AnalysisMode, LogLevel, TaskStatus

TaskInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
]


class TaskCreateRequest(BaseModel):
    conversation_id: UUID
    input_text: TaskInput
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=20)
    analysis_mode: Literal["demo", "model"] = "demo"


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    retry_of_task_id: UUID | None
    input_text: str
    input_payload_json: dict
    analysis_mode: AnalysisMode
    task_status: TaskStatus
    current_step: str | None
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None
    error_code: str | None
    error_message: str | None
    retryable: bool
    version: int
    created_at: datetime


class TaskCreateResponse(TaskResponse):
    websocket_required: bool = True


class TaskLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    sequence_no: int
    log_level: LogLevel
    log_type: str
    log_content: str
    created_at: datetime
