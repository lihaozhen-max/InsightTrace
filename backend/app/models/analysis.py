from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import APP_SCHEMA, Base
from app.models.common import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.models.enums import AnalysisMode, LogLevel, TaskStatus

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.identity import User


class AnalysisTask(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "analysis_tasks"
    __table_args__ = (
        Index(
            "uq_analysis_tasks_active_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("task_status IN ('queued', 'running')"),
        ),
        Index("ix_analysis_tasks_user_created", "user_id", "created_at"),
        Index("ix_analysis_tasks_status_created", "task_status", "created_at"),
        {"schema": APP_SCHEMA},
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    retry_of_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.analysis_tasks.id", ondelete="SET NULL"),
        index=True,
    )
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_payload_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    analysis_mode: Mapped[AnalysisMode] = mapped_column(
        enum_type(AnalysisMode, "analysis_mode"),
        nullable=False,
        default=AnalysisMode.DEMO,
        server_default=AnalysisMode.DEMO.value,
    )
    task_status: Mapped[TaskStatus] = mapped_column(
        enum_type(TaskStatus, "task_status"),
        nullable=False,
        default=TaskStatus.QUEUED,
        server_default=TaskStatus.QUEUED.value,
    )
    current_step: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    retryable: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    conversation: Mapped[Conversation] = relationship(back_populates="analysis_tasks")
    user: Mapped[User] = relationship(back_populates="analysis_tasks")
    retry_of_task: Mapped[AnalysisTask | None] = relationship(
        remote_side="AnalysisTask.id",
        back_populates="retry_tasks",
    )
    retry_tasks: Mapped[list[AnalysisTask]] = relationship(back_populates="retry_of_task")
    result: Mapped[AnalysisResult | None] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        uselist=False,
    )
    logs: Mapped[list[TaskLog]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskLog.sequence_no",
    )


class AnalysisResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        Index("ix_analysis_results_conversation_created", "conversation_id", "created_at"),
        {"schema": APP_SCHEMA},
    )

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.analysis_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    problem_definition: Mapped[str] = mapped_column(Text, nullable=False)
    key_metrics_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    evidence_list_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    conclusion_text: Mapped[str] = mapped_column(Text, nullable=False)
    missing_data_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    next_action_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    result_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    result_file_path: Mapped[str | None] = mapped_column(String(1000))
    result_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    generated_by: Mapped[AnalysisMode] = mapped_column(
        enum_type(AnalysisMode, "result_generated_by"),
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(Float)

    task: Mapped[AnalysisTask] = relationship(back_populates="result")
    conversation: Mapped[Conversation] = relationship(back_populates="analysis_results")


class TaskLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "task_logs"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence_no", name="uq_task_logs_task_sequence"),
        Index("ix_task_logs_task_created", "task_id", "created_at"),
        {"schema": APP_SCHEMA},
    )

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{APP_SCHEMA}.analysis_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    log_level: Mapped[LogLevel] = mapped_column(
        enum_type(LogLevel, "log_level"),
        nullable=False,
        default=LogLevel.INFO,
        server_default=LogLevel.INFO.value,
    )
    log_type: Mapped[str] = mapped_column(String(100), nullable=False)
    log_content: Mapped[str] = mapped_column(Text, nullable=False)

    task: Mapped[AnalysisTask] = relationship(back_populates="logs")
