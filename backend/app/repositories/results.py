from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisResult, AnalysisTask


async def get_for_user(
    session: AsyncSession,
    *,
    task_id: UUID,
    user_id: UUID,
    for_update: bool = False,
) -> AnalysisResult | None:
    statement = (
        select(AnalysisResult)
        .join(AnalysisTask, AnalysisTask.id == AnalysisResult.task_id)
        .where(
            AnalysisResult.task_id == task_id,
            AnalysisTask.user_id == user_id,
        )
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)
