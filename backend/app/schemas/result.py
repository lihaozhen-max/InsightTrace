from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AnalysisMode


class AnalysisResultResponse(BaseModel):
    id: UUID
    task_id: UUID
    conversation_id: UUID
    problem_definition: str
    key_metrics: list[dict[str, Any]]
    evidence_list: list[dict[str, Any]]
    conclusion_text: str
    missing_data_text: str
    next_actions: list[str]
    result_markdown: str
    result_version: int
    generated_by: AnalysisMode
    confidence: float | None
    report_available: bool
    created_at: datetime
    updated_at: datetime


class ResultExportResponse(BaseModel):
    task_id: UUID
    file_name: str
    download_path: str
