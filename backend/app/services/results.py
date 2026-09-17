from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ResourceNotFoundError
from app.models.analysis import AnalysisResult


def resolve_result_path(storage_root: Path, relative_path: str) -> Path:
    root = storage_root.resolve()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root / "exports"):
        raise ResourceNotFoundError("分析报告不存在")
    return candidate


def _write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.part")
    try:
        temporary_path.write_text(content, encoding="utf-8", newline="\n")
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


async def export_markdown_report(
    session: AsyncSession,
    result: AnalysisResult,
    *,
    storage_root: Path,
    user_id: UUID,
) -> Path:
    relative_path = Path(
        "exports",
        str(user_id),
        str(result.conversation_id),
        str(result.task_id),
        "report.md",
    ).as_posix()
    absolute_path = resolve_result_path(storage_root, relative_path)
    await asyncio.to_thread(_write_report, absolute_path, result.result_markdown)
    result.result_file_path = relative_path
    await session.commit()
    await session.refresh(result)
    return absolute_path
