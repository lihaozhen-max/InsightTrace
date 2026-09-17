from typing import Any

from pydantic import BaseModel


class ReadOnlyQueryResult(BaseModel):
    query_name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
