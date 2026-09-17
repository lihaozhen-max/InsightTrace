from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ResourceNotFoundError
from app.models.conversation import Attachment, Conversation
from app.models.enums import AttachmentParseStatus
from app.schemas.tool import (
    AttachmentContentSummary,
    AttachmentSearchHit,
    AttachmentSearchResult,
)

_TERM_PATTERN = re.compile(r"[\w\u3400-\u9fff]+", re.UNICODE)


def _display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _table_items(table: dict[str, Any], prefix: str = "") -> Iterable[tuple[str, str]]:
    rows = table.get("rows", [])
    if not isinstance(rows, list):
        return
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        content = " | ".join(
            f"{key}={_display_value(value)}" for key, value in row.items()
        )
        yield f"{prefix}row:{index}", content


def _json_items(value: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _json_items(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _json_items(child, f"{path}[{index}]")
    else:
        yield path, _display_value(value)


def iter_content_items(payload: dict[str, Any]) -> Iterable[tuple[str, str]]:
    kind = payload.get("kind")
    if kind == "table":
        yield from _table_items(payload)
    elif kind == "workbook":
        for sheet in payload.get("sheets", []):
            if isinstance(sheet, dict):
                name = str(sheet.get("name", "sheet"))
                yield from _table_items(sheet, f"sheet:{name}/")
    elif kind == "text":
        for index, line in enumerate(str(payload.get("content", "")).splitlines(), start=1):
            yield f"line:{index}", line
    elif kind == "json":
        yield from _json_items(payload.get("data"))


class AttachmentContentTool:
    def __init__(
        self,
        session: AsyncSession,
        *,
        max_scanned_items: int = 5_000,
        max_results: int = 20,
        max_snippet_chars: int = 500,
    ) -> None:
        if min(max_scanned_items, max_results, max_snippet_chars) <= 0:
            raise ValueError("Attachment search limits must be positive")
        self.session = session
        self.max_scanned_items = max_scanned_items
        self.max_results = max_results
        self.max_snippet_chars = max_snippet_chars

    async def _owned_attachment(
        self,
        *,
        attachment_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Attachment:
        attachment = await self.session.scalar(
            select(Attachment)
            .join(Conversation, Conversation.id == Attachment.conversation_id)
            .where(
                Attachment.id == attachment_id,
                Attachment.conversation_id == conversation_id,
                Conversation.user_id == user_id,
                Attachment.deleted_at.is_(None),
            )
        )
        if attachment is None:
            raise ResourceNotFoundError("附件不存在")
        if attachment.parse_status != AttachmentParseStatus.SUCCESS:
            raise AppError(
                code="ATTACHMENT_NOT_READY",
                message="附件尚未解析成功",
                status_code=409,
            )
        if not isinstance(attachment.parsed_content_json, dict):
            raise AppError(
                code="ATTACHMENT_CONTENT_MISSING",
                message="附件没有可读取的解析内容",
                status_code=409,
            )
        return attachment

    async def describe(
        self,
        *,
        attachment_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
    ) -> AttachmentContentSummary:
        attachment = await self._owned_attachment(
            attachment_id=attachment_id,
            conversation_id=conversation_id,
            user_id=user_id,
        )
        payload = attachment.parsed_content_json
        assert isinstance(payload, dict)
        columns = payload.get("columns", [])
        return AttachmentContentSummary(
            attachment_id=attachment.id,
            file_name=attachment.file_name,
            content_kind=str(payload.get("kind", "unknown")),
            source_format=str(payload.get("source_format", "unknown")),
            row_count=payload.get("row_count"),
            character_count=payload.get("character_count"),
            columns=[str(item) for item in columns] if isinstance(columns, list) else [],
        )

    async def search(
        self,
        *,
        attachment_id: UUID,
        conversation_id: UUID,
        user_id: UUID,
        query: str,
    ) -> AttachmentSearchResult:
        normalized_query = query.strip()
        terms = [term.casefold() for term in _TERM_PATTERN.findall(normalized_query)]
        if not terms:
            raise AppError(code="SEARCH_QUERY_EMPTY", message="检索词不能为空", status_code=422)
        attachment = await self._owned_attachment(
            attachment_id=attachment_id,
            conversation_id=conversation_id,
            user_id=user_id,
        )
        payload = attachment.parsed_content_json
        assert isinstance(payload, dict)
        ranked: list[AttachmentSearchHit] = []
        scanned_items = 0
        truncated = False
        for location, content in iter_content_items(payload):
            if scanned_items >= self.max_scanned_items:
                truncated = True
                break
            scanned_items += 1
            searchable = content.casefold()
            score = sum(searchable.count(term) for term in terms)
            if score:
                snippet = content[: self.max_snippet_chars]
                ranked.append(AttachmentSearchHit(location=location, snippet=snippet, score=score))
        ranked.sort(key=lambda item: (-item.score, item.location))
        if len(ranked) > self.max_results:
            truncated = True
        return AttachmentSearchResult(
            attachment_id=attachment.id,
            file_name=attachment.file_name,
            query=normalized_query,
            hits=ranked[: self.max_results],
            scanned_items=scanned_items,
            truncated=truncated,
        )
