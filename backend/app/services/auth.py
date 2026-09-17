from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole, UserStatus
from app.models.identity import User


@dataclass(frozen=True)
class MockIdentity:
    external_user_id: str
    username: str
    display_name: str
    role: UserRole


MOCK_IDENTITIES = {
    UserRole.ANALYST: MockIdentity(
        external_user_id="mock:analyst",
        username="demo.analyst",
        display_name="演示分析用户",
        role=UserRole.ANALYST,
    ),
    UserRole.ADMIN: MockIdentity(
        external_user_id="mock:admin",
        username="demo.admin",
        display_name="演示系统管理员",
        role=UserRole.ADMIN,
    ),
}


async def resolve_mock_user(session: AsyncSession, role: UserRole) -> User:
    identity = MOCK_IDENTITIES[role]
    result = await session.execute(
        select(User).where(User.external_user_id == identity.external_user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            external_user_id=identity.external_user_id,
            username=identity.username,
            display_name=identity.display_name,
            role=identity.role,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
    else:
        user.username = identity.username
        user.display_name = identity.display_name
        user.role = identity.role
        user.status = UserStatus.ACTIVE

    await session.commit()
    await session.refresh(user)
    return user
