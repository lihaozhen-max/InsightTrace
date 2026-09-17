from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Attachment


async def list_for_conversation(
    session: AsyncSession,
    conversation_id: UUID,
) -> list[Attachment]:
    result = await session.scalars(
        select(Attachment)
        .where(
            Attachment.conversation_id == conversation_id,
            Attachment.deleted_at.is_(None),
        )
        .order_by(Attachment.created_at.desc())
    )
    return list(result)


async def get_for_conversation(
    session: AsyncSession,
    *,
    attachment_id: UUID,
    conversation_id: UUID,
) -> Attachment | None:
    return await session.scalar(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.conversation_id == conversation_id,
            Attachment.deleted_at.is_(None),
        )
    )


async def total_size_for_conversation(
    session: AsyncSession,
    conversation_id: UUID,
) -> int:
    size = await session.scalar(
        select(func.coalesce(func.sum(Attachment.file_size), 0)).where(
            Attachment.conversation_id == conversation_id,
            Attachment.deleted_at.is_(None),
        )
    )
    return int(size or 0)


async def create_attachment(session: AsyncSession, attachment: Attachment) -> Attachment:
    session.add(attachment)
    await session.commit()
    await session.refresh(attachment)
    return attachment


async def delete_attachment(session: AsyncSession, attachment: Attachment) -> None:
    await session.delete(attachment)
    await session.commit()
