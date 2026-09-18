from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.redaction import redact_sensitive_text
from app.models.analysis import AnalysisTask, TaskLog
from app.models.conversation import Conversation
from app.models.enums import AnalysisMode, LogLevel, TaskStatus
from app.repositories.messages import create_user_message_pending

ACTIVE_TASK_STATUSES = (TaskStatus.QUEUED, TaskStatus.RUNNING)
TERMINAL_TASK_STATUSES = (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED)


async def list_for_conversation(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
) -> list[AnalysisTask]:
    result = await session.scalars(
        select(AnalysisTask)
        .where(
            AnalysisTask.conversation_id == conversation_id,
            AnalysisTask.user_id == user_id,
        )
        .order_by(AnalysisTask.created_at.desc())
    )
    return list(result)


async def get_latest_for_conversation(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
) -> AnalysisTask | None:
    return await session.scalar(
        select(AnalysisTask)
        .where(
            AnalysisTask.conversation_id == conversation_id,
            AnalysisTask.user_id == user_id,
        )
        .order_by(AnalysisTask.created_at.desc())
        .limit(1)
    )


async def get_for_user(
    session: AsyncSession,
    *,
    task_id: UUID,
    user_id: UUID,
    for_update: bool = False,
) -> AnalysisTask | None:
    statement = select(AnalysisTask).where(
        AnalysisTask.id == task_id,
        AnalysisTask.user_id == user_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def list_logs(session: AsyncSession, task_id: UUID) -> list[TaskLog]:
    result = await session.scalars(
        select(TaskLog)
        .where(TaskLog.task_id == task_id)
        .order_by(TaskLog.sequence_no)
    )
    return list(result)


async def list_logs_after(
    session: AsyncSession,
    task_id: UUID,
    sequence_no: int,
) -> list[TaskLog]:
    result = await session.scalars(
        select(TaskLog)
        .where(
            TaskLog.task_id == task_id,
            TaskLog.sequence_no > sequence_no,
        )
        .order_by(TaskLog.sequence_no)
    )
    return list(result)


async def _next_log_sequence(session: AsyncSession, task_id: UUID) -> int:
    current = await session.scalar(
        select(func.max(TaskLog.sequence_no)).where(TaskLog.task_id == task_id)
    )
    return int(current or 0) + 1


async def append_log(
    session: AsyncSession,
    task: AnalysisTask,
    *,
    log_type: str,
    content: str,
    level: LogLevel = LogLevel.INFO,
) -> TaskLog:
    log = TaskLog(
        task_id=task.id,
        sequence_no=await _next_log_sequence(session, task.id),
        log_level=level,
        log_type=log_type,
        log_content=redact_sensitive_text(content),
    )
    session.add(log)
    await session.flush()
    return log


async def create_task(
    session: AsyncSession,
    *,
    conversation: Conversation,
    user_id: UUID,
    input_text: str,
    attachment_ids: list[UUID],
    analysis_mode: AnalysisMode,
    retry_of_task_id: UUID | None = None,
    save_user_message: bool = True,
) -> AnalysisTask:
    active_task = await session.scalar(
        select(AnalysisTask.id).where(
            AnalysisTask.conversation_id == conversation.id,
            AnalysisTask.task_status.in_(ACTIVE_TASK_STATUSES),
        )
    )
    if active_task is not None:
        raise AppError(
            code="TASK_ALREADY_ACTIVE",
            message="该会话已有正在排队或运行的分析任务",
            status_code=409,
        )

    message_id = None
    if save_user_message:
        message = await create_user_message_pending(
            session,
            conversation=conversation,
            content=input_text,
        )
        message_id = str(message.id)

    task = AnalysisTask(
        conversation_id=conversation.id,
        user_id=user_id,
        retry_of_task_id=retry_of_task_id,
        input_text=input_text,
        input_payload_json={
            "attachment_ids": [str(item) for item in attachment_ids],
            "message_id": message_id,
        },
        analysis_mode=analysis_mode,
        task_status=TaskStatus.QUEUED,
    )
    session.add(task)
    try:
        await session.flush()
        await append_log(
            session,
            task,
            log_type="task_queued",
            content="分析任务已进入队列",
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise AppError(
            code="TASK_ALREADY_ACTIVE",
            message="该会话已有正在排队或运行的分析任务",
            status_code=409,
        ) from error
    await session.refresh(task)
    return task


async def cancel_task(session: AsyncSession, task: AnalysisTask) -> AnalysisTask:
    if task.task_status not in ACTIVE_TASK_STATUSES:
        raise AppError(
            code="TASK_NOT_CANCELLABLE",
            message="只有排队中或运行中的任务可以取消",
            status_code=409,
        )

    now = datetime.now(UTC)
    task.cancel_requested_at = now
    task.version += 1
    if task.task_status == TaskStatus.QUEUED:
        task.task_status = TaskStatus.CANCELLED
        task.finished_at = now
        task.current_step = None
        log_type = "task_cancelled"
        content = "排队中的分析任务已取消"
    else:
        log_type = "cancel_requested"
        content = "已请求取消运行中的分析任务"
    await append_log(session, task, log_type=log_type, content=content)
    await session.commit()
    await session.refresh(task)
    return task
