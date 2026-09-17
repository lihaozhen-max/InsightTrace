from typing import Any, Literal
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


class MetricDefinition(BaseModel):
    metric_name: str
    operation: Literal["count", "sum", "average", "minimum", "maximum", "ratio"]
    value_field: str | None = None
    numerator_field: str | None = None
    denominator_field: str | None = None
    group_by: list[str] = Field(default_factory=list, max_length=3)
    filters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    unit: str = ""
    ratio_scale: float = 100.0


class MetricPoint(BaseModel):
    dimensions: dict[str, str]
    value: float
    unit: str
    rows_used: int
    rows_skipped: int


class MetricCalculationResult(BaseModel):
    metric_name: str
    operation: str
    points: list[MetricPoint]
    total_rows: int
    matched_rows: int
