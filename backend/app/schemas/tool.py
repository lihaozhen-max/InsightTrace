from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ReadOnlyQueryResult(BaseModel):
    query_name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool


class AttachmentContentSummary(BaseModel):
    attachment_id: UUID
    file_name: str
    content_kind: str
    source_format: str
    row_count: int | None = None
    character_count: int | None = None
    columns: list[str] = Field(default_factory=list)


class AttachmentSearchHit(BaseModel):
    location: str
    snippet: str
    score: int


class AttachmentSearchResult(BaseModel):
    attachment_id: UUID
    file_name: str
    query: str
    hits: list[AttachmentSearchHit]
    scanned_items: int
    truncated: bool
