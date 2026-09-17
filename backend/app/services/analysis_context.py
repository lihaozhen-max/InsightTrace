from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.analysis import AnalysisResult, AnalysisTask
from app.models.conversation import Attachment, ContextSummary, Message
from app.models.enums import AttachmentParseStatus
from app.schemas.context import (
    AnalysisContext,
    ContextAttachment,
    ContextMessage,
    PreviousAnalysisContext,
)

ROLE_LABELS = {"user": "用户", "assistant": "分析助手", "system": "系统", "tool": "工具"}


def summarize_messages(messages: list[Message], *, max_chars: int = 4_000) -> str:
    sections: list[str] = []
    used = 0
    for message in messages:
        normalized = " ".join(message.content.split())
        item = f"{ROLE_LABELS[message.role.value]}[{message.seq_no}]：{normalized}"
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(item) > remaining:
            item = item[: max(0, remaining - 1)] + "…"
        sections.append(item)
        used += len(item) + 1
    return "\n".join(sections)


async def _load_or_create_summary(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    older_messages: list[Message],
    max_chars: int,
) -> str | None:
    if not older_messages:
        return None
    start_seq_no = older_messages[0].seq_no
    end_seq_no = older_messages[-1].seq_no
    existing = await session.scalar(
        select(ContextSummary).where(
            ContextSummary.conversation_id == conversation_id,
            ContextSummary.start_seq_no == start_seq_no,
            ContextSummary.end_seq_no == end_seq_no,
        )
    )
    if existing is not None:
        return existing.summary_text
    summary_text = summarize_messages(older_messages, max_chars=max_chars)
    session.add(
        ContextSummary(
            conversation_id=conversation_id,
            start_seq_no=start_seq_no,
            end_seq_no=end_seq_no,
            summary_text=summary_text,
        )
    )
    await session.flush()
    return summary_text


async def assemble_analysis_context(
    session: AsyncSession,
    task: AnalysisTask,
    *,
    recent_message_limit: int = 8,
    summary_max_chars: int = 4_000,
    message_max_chars: int = 2_000,
) -> AnalysisContext:
    if recent_message_limit <= 0 or summary_max_chars <= 0 or message_max_chars <= 0:
        raise ValueError("Context limits must be positive")
    messages = list(
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == task.conversation_id)
            .order_by(Message.seq_no)
        )
    )
    older_messages = messages[:-recent_message_limit]
    recent_messages = messages[-recent_message_limit:]
    earlier_summary = await _load_or_create_summary(
        session,
        conversation_id=task.conversation_id,
        older_messages=older_messages,
        max_chars=summary_max_chars,
    )

    previous_result = await session.scalar(
        select(AnalysisResult)
        .where(
            AnalysisResult.conversation_id == task.conversation_id,
            AnalysisResult.task_id != task.id,
        )
        .order_by(AnalysisResult.created_at.desc())
        .limit(1)
    )
    previous_analysis = None
    if previous_result is not None:
        previous_analysis = PreviousAnalysisContext(
            problem_definition=previous_result.problem_definition,
            conclusion_text=previous_result.conclusion_text,
            key_metrics=previous_result.key_metrics_json,
            evidence_list=previous_result.evidence_list_json,
        )

    raw_attachment_ids = task.input_payload_json.get("attachment_ids", [])
    try:
        attachment_ids = [UUID(value) for value in raw_attachment_ids]
    except (TypeError, ValueError) as error:
        raise AppError(
            code="TASK_INPUT_INVALID",
            message="任务中的附件输入快照无效",
            status_code=409,
        ) from error
    attachments: list[Attachment] = []
    if attachment_ids:
        attachments = list(
            await session.scalars(
                select(Attachment).where(
                    Attachment.id.in_(attachment_ids),
                    Attachment.conversation_id == task.conversation_id,
                    Attachment.deleted_at.is_(None),
                    Attachment.parse_status == AttachmentParseStatus.SUCCESS,
                )
            )
        )
    if len(attachments) != len(attachment_ids):
        raise AppError(
            code="TASK_ATTACHMENT_UNAVAILABLE",
            message="任务关联的一个或多个附件已不可用",
            status_code=409,
        )

    attachment_contexts: list[ContextAttachment] = []
    for attachment in attachments:
        payload = attachment.parsed_content_json
        if not isinstance(payload, dict):
            continue
        columns = payload.get("columns", [])
        attachment_contexts.append(
            ContextAttachment(
                attachment_id=attachment.id,
                file_name=attachment.file_name,
                content_kind=str(payload.get("kind", "unknown")),
                source_format=str(payload.get("source_format", "unknown")),
                row_count=payload.get("row_count"),
                columns=[str(item) for item in columns] if isinstance(columns, list) else [],
            )
        )

    return AnalysisContext(
        conversation_id=task.conversation_id,
        task_id=task.id,
        current_question=task.input_text,
        earlier_summary=earlier_summary,
        recent_messages=[
            ContextMessage(
                seq_no=message.seq_no,
                role=message.role,
                content=message.content[:message_max_chars],
            )
            for message in recent_messages
        ],
        previous_analysis=previous_analysis,
        attachments=attachment_contexts,
    )
