from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.enums import ConversationStatus


async def list_for_user(session: AsyncSession, user_id: UUID) -> list[Conversation]:
    result = await session.scalars(
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.status != ConversationStatus.DELETED,
        )
        .order_by(Conversation.updated_at.desc())
    )
    return list(result)


async def create_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    title: str,
) -> Conversation:
    conversation = Conversation(user_id=user_id, title=title)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation
