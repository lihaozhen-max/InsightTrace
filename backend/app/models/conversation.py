from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import APP_SCHEMA, Base
from app.models.common import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.models.enums import (
    AttachmentParseStatus,
    ConversationStatus,
    MessageRole,
    MessageType,
    ToolStatus,
)

if TYPE_CHECKING:
    from app.models.analysis import AnalysisResult, AnalysisTask
    from app.models.identity import User, WebSocketToken


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_last_message", "user_id", "last_message_at"),
        {"schema": APP_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        enum_type(ConversationStatus, "conversation_status"),
        nullable=False,
        default=ConversationStatus.ACTIVE,
        server_default=ConversationStatus.ACTIVE.value,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.seq_no",
    )
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    analysis_tasks: Mapped[list[AnalysisTask]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    analysis_results: Mapped[list[AnalysisResult]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    context_summaries: Mapped[list[ContextSummary]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    websocket_tokens: Mapped[list[WebSocketToken]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq_no", name="uq_messages_conversation_seq"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        {"schema": APP_SCHEMA},
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        enum_type(MessageRole, "message_role"),
        nullable=False,
    )
    message_type: Mapped[MessageType] = mapped_column(
        enum_type(MessageType, "message_type"),
        nullable=False,
        default=MessageType.TEXT,
        server_default=MessageType.TEXT.value,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(100))
    tool_status: Mapped[ToolStatus | None] = mapped_column(
        enum_type(ToolStatus, "tool_status")
    )
    seq_no: Mapped[int] = mapped_column(BigInteger, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    attachments: Mapped[list[Attachment]] = relationship(back_populates="message")


class Attachment(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("file_size >= 0", name="file_size_non_negative"),
        Index("ix_attachments_conversation_created", "conversation_id", "created_at"),
        {"schema": APP_SCHEMA},
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.messages.id", ondelete="SET NULL"),
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_status: Mapped[AttachmentParseStatus] = mapped_column(
        enum_type(AttachmentParseStatus, "attachment_parse_status"),
        nullable=False,
        default=AttachmentParseStatus.PENDING,
        server_default=AttachmentParseStatus.PENDING.value,
    )
    parse_error: Mapped[str | None] = mapped_column(Text)
    parsed_content_json: Mapped[dict | list | None] = mapped_column(JSONB)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conversation: Mapped[Conversation] = relationship(back_populates="attachments")
    message: Mapped[Message | None] = relationship(back_populates="attachments")


class ContextSummary(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "context_summaries"
    __table_args__ = (
        CheckConstraint("start_seq_no >= 1", name="start_seq_positive"),
        CheckConstraint("end_seq_no >= start_seq_no", name="summary_range_valid"),
        UniqueConstraint(
            "conversation_id",
            "start_seq_no",
            "end_seq_no",
            name="uq_context_summaries_range",
        ),
        {"schema": APP_SCHEMA},
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_seq_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_seq_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="context_summaries")
