from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message
from app.models.enums import MessageRole, MessageType


async def list_for_conversation(
    session: AsyncSession,
    conversation_id: UUID,
) -> list[Message]:
    result = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq_no)
    )
    return list(result)


async def create_user_message(
    session: AsyncSession,
    *,
    conversation: Conversation,
    content: str,
) -> Message:
    message = await create_user_message_pending(
        session,
        conversation=conversation,
        content=content,
    )
    await session.commit()
    await session.refresh(message)
    return message


async def create_user_message_pending(
    session: AsyncSession,
    *,
    conversation: Conversation,
    content: str,
) -> Message:
    last_seq_no = await session.scalar(
        select(func.max(Message.seq_no)).where(
            Message.conversation_id == conversation.id
        )
    )
    message = Message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        message_type=MessageType.TEXT,
        content=content,
        seq_no=(last_seq_no or 0) + 1,
    )
    conversation.last_message_at = datetime.now(UTC)
    session.add(message)
    await session.flush()
    return message
