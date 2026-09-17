from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import WebSocketToken


async def create_token(
    session: AsyncSession,
    *,
    user_id: UUID,
    conversation_id: UUID,
    token_hash: str,
    expires_at: datetime,
) -> WebSocketToken:
    await session.execute(
        delete(WebSocketToken).where(
            WebSocketToken.user_id == user_id,
            WebSocketToken.conversation_id == conversation_id,
            WebSocketToken.consumed_at.is_(None),
        )
    )
    token = WebSocketToken(
        user_id=user_id,
        conversation_id=conversation_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    session.add(token)
    await session.commit()
    await session.refresh(token)
    return token


async def consume_token(
    session: AsyncSession,
    *,
    token_hash: str,
    conversation_id: UUID,
) -> WebSocketToken | None:
    now = datetime.now(UTC)
    token = await session.scalar(
        select(WebSocketToken)
        .where(
            WebSocketToken.token_hash == token_hash,
            WebSocketToken.conversation_id == conversation_id,
            WebSocketToken.consumed_at.is_(None),
            WebSocketToken.expires_at > now,
        )
        .with_for_update()
    )
    if token is None:
        return None
    token.consumed_at = now
    await session.commit()
    await session.refresh(token)
    return token
