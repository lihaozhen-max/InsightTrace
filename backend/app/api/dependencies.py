from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnauthenticatedError
from app.db.dependencies import get_db_session
from app.models.enums import UserRole, UserStatus
from app.models.identity import User

DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(request: Request, session: DatabaseSession) -> User:
    raw_user_id = request.session.get("user_id")
    if not raw_user_id:
        raise UnauthenticatedError()

    try:
        user_id = UUID(raw_user_id)
    except (TypeError, ValueError) as error:
        request.session.clear()
        raise UnauthenticatedError("登录状态无效，请重新登录") from error

    result = await session.execute(
        select(User).where(
            User.id == user_id,
            User.status == UserStatus.ACTIVE,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        request.session.clear()
        raise UnauthenticatedError("登录已失效，请重新登录")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError()
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
