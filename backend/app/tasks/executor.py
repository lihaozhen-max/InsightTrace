from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from uuid import UUID, uuid4

from sqlalchemy import select

from app.analysis.demo import build_demo_analysis
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models.analysis import AnalysisTask
from app.models.conversation import Attachment
from app.models.enums import TaskStatus
from app.services.analysis_context import assemble_analysis_context
from app.services.task_lifecycle import (
    advance_task,
    complete_task,
    fail_task,
    finish_cancelled_task,
    record_task_event,
    start_task,
)

logger = logging.getLogger(__name__)


async def _claim_next_task() -> UUID | None:
    async with SessionLocal() as session:
        task = await session.scalar(
            select(AnalysisTask)
            .where(AnalysisTask.task_status == TaskStatus.QUEUED)
            .order_by(AnalysisTask.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if task is None:
            return None
        await start_task(session, task)
        return task.id


async def _finish_as_cancelled(task_id: UUID) -> None:
    async with SessionLocal() as session:
        task = await session.scalar(
            select(AnalysisTask)
            .where(AnalysisTask.id == task_id)
            .with_for_update()
        )
        if (
            task is not None
            and task.task_status == TaskStatus.RUNNING
            and task.cancel_requested_at is not None
        ):
            await finish_cancelled_task(session, task)


async def _finish_as_failed(task_id: UUID, error: Exception) -> None:
    async with SessionLocal() as session:
        task = await session.scalar(
            select(AnalysisTask)
            .where(AnalysisTask.id == task_id)
            .with_for_update()
        )
        if task is None or task.task_status not in (TaskStatus.QUEUED, TaskStatus.RUNNING):
            return
        await fail_task(
            session,
            task,
            error_code="TASK_EXECUTION_FAILED",
            error_message="分析任务执行失败，请稍后重试",
            retryable=True,
        )
    logger.exception("Analysis task failed task_id=%s", task_id, exc_info=error)


async def execute_task(task_id: UUID) -> None:
    try:
        async with SessionLocal() as session:
            task = await session.get(AnalysisTask, task_id)
            if task is None or task.task_status != TaskStatus.RUNNING:
                return

            await assemble_analysis_context(session, task)
            stream_id = str(uuid4())
            await record_task_event(
                session,
                task,
                event_type="message_start",
                payload={"message_id": stream_id},
            )
            await advance_task(
                session,
                task,
                step="inspecting_sources",
                description="正在检查本轮选择的数据源",
            )
            tool_call_id = str(uuid4())
            await record_task_event(
                session,
                task,
                event_type="tool_start",
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": "attachment_inspector",
                    "summary": "检查已解析附件的结构和规模",
                },
            )
            attachment_ids = [
                UUID(value) for value in task.input_payload_json.get("attachment_ids", [])
            ]
            attachments = list(
                await session.scalars(
                    select(Attachment).where(
                        Attachment.id.in_(attachment_ids),
                        Attachment.conversation_id == task.conversation_id,
                        Attachment.deleted_at.is_(None),
                    )
                )
            ) if attachment_ids else []
            await record_task_event(
                session,
                task,
                event_type="tool_finish",
                payload={
                    "tool_call_id": tool_call_id,
                    "tool_name": "attachment_inspector",
                    "status": "success",
                    "result_summary": f"已检查 {len(attachments)} 个附件",
                },
            )
            await advance_task(
                session,
                task,
                step="calculating_metrics",
                description="正在生成演示模式的数据概览",
            )
            output = build_demo_analysis(task.input_text, attachments)
            await advance_task(
                session,
                task,
                step="building_evidence",
                description="正在整理证据与缺失信息",
            )
            await advance_task(
                session,
                task,
                step="generating_conclusion",
                description="正在生成结构化结论",
            )
            for delta in (
                "数据源检查已完成。",
                output.conclusion_text,
                f"下一步建议：{'；'.join(output.next_actions)}",
            ):
                await record_task_event(
                    session,
                    task,
                    event_type="message_delta",
                    payload={"message_id": stream_id, "delta_text": delta},
                )
            await advance_task(
                session,
                task,
                step="saving_result",
                description="正在保存分析结果和助手消息",
            )
            await complete_task(
                session,
                task,
                problem_definition=output.problem_definition,
                key_metrics=output.key_metrics,
                evidence_list=output.evidence_list,
                conclusion_text=output.conclusion_text,
                missing_data_text=output.missing_data_text,
                next_action_text=output.next_action_text,
                result_markdown=output.result_markdown,
                assistant_message=output.result_markdown,
                confidence=output.overall_confidence,
            )
    except AppError as error:
        if error.code == "TASK_CANCEL_REQUESTED":
            await _finish_as_cancelled(task_id)
            return
        await _finish_as_failed(task_id, error)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        await _finish_as_failed(task_id, error)


async def process_next_queued_task() -> bool:
    task_id = await _claim_next_task()
    if task_id is None:
        return False
    await execute_task(task_id)
    return True


class TaskExecutor:
    def __init__(self, poll_interval_seconds: float = 0.5) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._stop_requested = asyncio.Event()

    async def run(self) -> None:
        while not self._stop_requested.is_set():
            processed = await process_next_queued_task()
            if processed:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop_requested.wait(),
                    timeout=self.poll_interval_seconds,
                )

    def stop(self) -> None:
        self._stop_requested.set()
