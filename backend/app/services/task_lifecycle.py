from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.analysis import AnalysisResult, AnalysisTask
from app.models.conversation import Conversation
from app.models.enums import LogLevel, TaskStatus
from app.repositories.messages import create_assistant_message_pending
from app.repositories.tasks import append_log

TASK_STEPS = (
    "preparing_context",
    "inspecting_sources",
    "querying_data",
    "calculating_metrics",
    "building_evidence",
    "generating_conclusion",
    "saving_result",
)


def _require_status(task: AnalysisTask, *allowed: TaskStatus) -> None:
    if task.task_status not in allowed:
        raise AppError(
            code="TASK_STATE_CONFLICT",
            message=f"任务当前状态 {task.task_status.value} 不允许执行该操作",
            status_code=409,
        )


async def start_task(session: AsyncSession, task: AnalysisTask) -> AnalysisTask:
    _require_status(task, TaskStatus.QUEUED)
    now = datetime.now(UTC)
    task.task_status = TaskStatus.RUNNING
    task.current_step = "preparing_context"
    task.started_at = now
    task.version += 1
    await append_log(
        session,
        task,
        log_type="task_started",
        content="分析任务开始执行",
    )
    await session.commit()
    await session.refresh(task)
    return task


async def advance_task(
    session: AsyncSession,
    task: AnalysisTask,
    *,
    step: str,
    description: str,
) -> AnalysisTask:
    _require_status(task, TaskStatus.RUNNING)
    if step not in TASK_STEPS:
        raise AppError(
            code="TASK_STEP_INVALID",
            message="任务步骤不在允许范围内",
            status_code=422,
        )
    if task.cancel_requested_at is not None:
        raise AppError(
            code="TASK_CANCEL_REQUESTED",
            message="任务已请求取消，不能进入下一步骤",
            status_code=409,
        )
    task.current_step = step
    task.version += 1
    await append_log(
        session,
        task,
        log_type="task_step",
        content=description,
    )
    await session.commit()
    await session.refresh(task)
    return task


async def fail_task(
    session: AsyncSession,
    task: AnalysisTask,
    *,
    error_code: str,
    error_message: str,
    retryable: bool,
) -> AnalysisTask:
    _require_status(task, TaskStatus.QUEUED, TaskStatus.RUNNING)
    task.task_status = TaskStatus.FAILED
    task.finished_at = datetime.now(UTC)
    task.error_code = error_code
    task.error_message = error_message
    task.retryable = retryable
    task.version += 1
    await append_log(
        session,
        task,
        log_type="task_failed",
        content=error_message,
        level=LogLevel.ERROR,
    )
    await session.commit()
    await session.refresh(task)
    return task


async def finish_cancelled_task(
    session: AsyncSession,
    task: AnalysisTask,
) -> AnalysisTask:
    _require_status(task, TaskStatus.RUNNING)
    if task.cancel_requested_at is None:
        raise AppError(
            code="TASK_CANCEL_NOT_REQUESTED",
            message="任务尚未请求取消",
            status_code=409,
        )
    task.task_status = TaskStatus.CANCELLED
    task.finished_at = datetime.now(UTC)
    task.current_step = None
    task.version += 1
    await append_log(
        session,
        task,
        log_type="task_cancelled",
        content="运行中的分析任务已安全停止",
    )
    await session.commit()
    await session.refresh(task)
    return task


async def complete_task(
    session: AsyncSession,
    task: AnalysisTask,
    *,
    problem_definition: str,
    key_metrics: list[dict[str, Any]],
    evidence_list: list[dict[str, Any]],
    conclusion_text: str,
    missing_data_text: str,
    next_action_text: str,
    result_markdown: str,
    assistant_message: str,
    confidence: float | None = None,
) -> AnalysisResult:
    _require_status(task, TaskStatus.RUNNING)
    if task.cancel_requested_at is not None:
        raise AppError(
            code="TASK_CANCEL_REQUESTED",
            message="任务已请求取消，不能保存成功结果",
            status_code=409,
        )
    conversation = await session.scalar(
        select(Conversation)
        .where(Conversation.id == task.conversation_id)
        .with_for_update()
    )
    if conversation is None:
        raise AppError(
            code="CONVERSATION_MISSING",
            message="任务所属会话不存在",
            status_code=409,
        )

    result = AnalysisResult(
        task_id=task.id,
        conversation_id=task.conversation_id,
        problem_definition=problem_definition,
        key_metrics_json=key_metrics,
        evidence_list_json=evidence_list,
        conclusion_text=conclusion_text,
        missing_data_text=missing_data_text,
        next_action_text=next_action_text,
        result_markdown=result_markdown,
        generated_by=task.analysis_mode,
        confidence=confidence,
    )
    session.add(result)
    await create_assistant_message_pending(
        session,
        conversation=conversation,
        content=assistant_message,
    )
    task.task_status = TaskStatus.SUCCESS
    task.current_step = None
    task.finished_at = datetime.now(UTC)
    task.retryable = False
    task.version += 1
    await append_log(
        session,
        task,
        log_type="task_succeeded",
        content="分析结果和助手消息已保存",
    )
    await session.commit()
    await session.refresh(result)
    return result
