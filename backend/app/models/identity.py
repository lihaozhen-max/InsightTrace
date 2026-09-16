from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import APP_SCHEMA, Base
from app.models.common import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.models.enums import UserRole, UserStatus

if TYPE_CHECKING:
    from app.models.analysis import AnalysisTask
    from app.models.conversation import Conversation


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_external_user_id", "external_user_id", unique=True),
        Index("ix_users_username", "username", unique=True),
        {"schema": APP_SCHEMA},
    )

    external_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        enum_type(UserRole, "user_role"),
        nullable=False,
        default=UserRole.ANALYST,
        server_default=UserRole.ANALYST.value,
    )
    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus, "user_status"),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    analysis_tasks: Mapped[list[AnalysisTask]] = relationship(back_populates="user")
    websocket_tokens: Mapped[list[WebSocketToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class WebSocketToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "websocket_tokens"
    __table_args__ = (
        Index("ix_websocket_tokens_token_hash", "token_hash", unique=True),
        Index("ix_websocket_tokens_expires_at", "expires_at"),
        {"schema": APP_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="websocket_tokens")
    conversation: Mapped[Conversation] = relationship(back_populates="websocket_tokens")
