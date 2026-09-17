from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MessageRole


class ContextMessage(BaseModel):
    seq_no: int
    role: MessageRole
    content: str


class ContextAttachment(BaseModel):
    attachment_id: UUID
    file_name: str
    content_kind: str
    source_format: str
    row_count: int | None = None
    columns: list[str] = Field(default_factory=list)


class PreviousAnalysisContext(BaseModel):
    problem_definition: str
    conclusion_text: str
    key_metrics: list[dict[str, Any]]
    evidence_list: list[dict[str, Any]]


class AnalysisContext(BaseModel):
    conversation_id: UUID
    task_id: UUID
    current_question: str
    earlier_summary: str | None
    recent_messages: list[ContextMessage]
    previous_analysis: PreviousAnalysisContext | None
    attachments: list[ContextAttachment]
