from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.analysis import AnalysisTask
from app.models.enums import TaskStatus
from app.services.task_lifecycle import fail_task


async def recover_interrupted_tasks() -> int:
    async with SessionLocal() as session:
        tasks = list(
            await session.scalars(
                select(AnalysisTask)
                .where(AnalysisTask.task_status == TaskStatus.RUNNING)
                .with_for_update()
            )
        )
        for task in tasks:
            await fail_task(
                session,
                task,
                error_code="WORKER_RESTARTED",
                error_message="后端服务重启，运行中的任务已安全终止，可重新分析",
                retryable=True,
            )
        return len(tasks)
