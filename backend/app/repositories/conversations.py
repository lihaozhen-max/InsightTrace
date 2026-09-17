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


async def get_for_user(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
    for_update: bool = False,
) -> Conversation | None:
    statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
        Conversation.status != ConversationStatus.DELETED,
    )
    if for_update:
        statement = statement.with_for_update()

    return await session.scalar(statement)


async def update_conversation(
    session: AsyncSession,
    conversation: Conversation,
) -> Conversation:
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def delete_conversation(
    session: AsyncSession,
    conversation: Conversation,
) -> None:
    await session.delete(conversation)
    await session.commit()
