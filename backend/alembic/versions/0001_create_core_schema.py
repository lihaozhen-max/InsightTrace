"""Create the InsightTrace core schema.

Revision ID: 0001_core_schema
Revises:
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_core_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "insighttrace"


def enum_type(*values: str, name: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def id_column() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def created_at_column() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def updated_at_column() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "users",
        id_column(),
        sa.Column("external_user_id", sa.String(128), nullable=False),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column(
            "role",
            enum_type("analyst", "admin", name="user_role"),
            nullable=False,
            server_default="analyst",
        ),
        sa.Column(
            "status",
            enum_type("active", "disabled", name="user_status"),
            nullable=False,
            server_default="active",
        ),
        created_at_column(),
        updated_at_column(),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_users_external_user_id",
        "users",
        ["external_user_id"],
        unique=True,
        schema=SCHEMA,
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True, schema=SCHEMA)

    op.create_table(
        "conversations",
        id_column(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column(
            "status",
            enum_type("active", "archived", "deleted", name="conversation_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        created_at_column(),
        updated_at_column(),
        schema=SCHEMA,
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"], schema=SCHEMA)
    op.create_index(
        "ix_conversations_user_last_message",
        "conversations",
        ["user_id", "last_message_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "messages",
        id_column(),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            enum_type("user", "assistant", "system", "tool", name="message_role"),
            nullable=False,
        ),
        sa.Column(
            "message_type",
            enum_type("text", "status", "tool", "error", name="message_type"),
            nullable=False,
            server_default="text",
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(100)),
        sa.Column(
            "tool_status",
            enum_type("started", "success", "failed", name="tool_status"),
        ),
        sa.Column("seq_no", sa.BigInteger(), nullable=False),
        created_at_column(),
        sa.UniqueConstraint(
            "conversation_id",
            "seq_no",
            name="uq_messages_conversation_seq",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"], schema=SCHEMA)
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "attachments",
        id_column(),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.messages.id", ondelete="SET NULL"),
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "parse_status",
            enum_type("pending", "parsing", "success", "failed", name="attachment_parse_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("parse_error", sa.Text()),
        sa.Column("parsed_content_json", postgresql.JSONB()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        created_at_column(),
        sa.CheckConstraint("file_size >= 0", name="ck_attachments_file_size_non_negative"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_attachments_conversation_id",
        "attachments",
        ["conversation_id"],
        schema=SCHEMA,
    )
    op.create_index("ix_attachments_message_id", "attachments", ["message_id"], schema=SCHEMA)
    op.create_index(
        "ix_attachments_conversation_created",
        "attachments",
        ["conversation_id", "created_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "analysis_tasks",
        id_column(),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "retry_of_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.analysis_tasks.id", ondelete="SET NULL"),
        ),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column(
            "input_payload_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "analysis_mode",
            enum_type("demo", "model", name="analysis_mode"),
            nullable=False,
            server_default="demo",
        ),
        sa.Column(
            "task_status",
            enum_type("queued", "running", "success", "failed", "cancelled", name="task_status"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("current_step", sa.String(100)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        created_at_column(),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_analysis_tasks_conversation_id",
        "analysis_tasks",
        ["conversation_id"],
        schema=SCHEMA,
    )
    op.create_index("ix_analysis_tasks_user_id", "analysis_tasks", ["user_id"], schema=SCHEMA)
    op.create_index(
        "ix_analysis_tasks_retry_of_task_id",
        "analysis_tasks",
        ["retry_of_task_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_analysis_tasks_user_created",
        "analysis_tasks",
        ["user_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_analysis_tasks_status_created",
        "analysis_tasks",
        ["task_status", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "uq_analysis_tasks_active_conversation",
        "analysis_tasks",
        ["conversation_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("task_status IN ('queued', 'running')"),
    )

    op.create_table(
        "analysis_results",
        id_column(),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("problem_definition", sa.Text(), nullable=False),
        sa.Column("key_metrics_json", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_list_json", postgresql.JSONB(), nullable=False),
        sa.Column("conclusion_text", sa.Text(), nullable=False),
        sa.Column("missing_data_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("next_action_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("result_markdown", sa.Text(), nullable=False),
        sa.Column("result_file_path", sa.String(1000)),
        sa.Column("result_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "generated_by",
            enum_type("demo", "model", name="result_generated_by"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float()),
        created_at_column(),
        updated_at_column(),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_analysis_results_confidence_range",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_analysis_results_conversation_id",
        "analysis_results",
        ["conversation_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_analysis_results_conversation_created",
        "analysis_results",
        ["conversation_id", "created_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "context_summaries",
        id_column(),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_seq_no", sa.BigInteger(), nullable=False),
        sa.Column("end_seq_no", sa.BigInteger(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        created_at_column(),
        sa.CheckConstraint("start_seq_no >= 1", name="ck_context_summaries_start_seq_positive"),
        sa.CheckConstraint(
            "end_seq_no >= start_seq_no",
            name="ck_context_summaries_summary_range_valid",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "start_seq_no",
            "end_seq_no",
            name="uq_context_summaries_range",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_context_summaries_conversation_id",
        "context_summaries",
        ["conversation_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "websocket_tokens",
        id_column(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        created_at_column(),
        schema=SCHEMA,
    )
    op.create_index("ix_websocket_tokens_user_id", "websocket_tokens", ["user_id"], schema=SCHEMA)
    op.create_index(
        "ix_websocket_tokens_conversation_id",
        "websocket_tokens",
        ["conversation_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_websocket_tokens_token_hash",
        "websocket_tokens",
        ["token_hash"],
        unique=True,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_websocket_tokens_expires_at",
        "websocket_tokens",
        ["expires_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "system_configs",
        id_column(),
        sa.Column("config_key", sa.String(200), nullable=False),
        sa.Column("config_value", sa.Text(), nullable=False),
        sa.Column("config_group", sa.String(100), nullable=False),
        created_at_column(),
        updated_at_column(),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_system_configs_key",
        "system_configs",
        ["config_key"],
        unique=True,
        schema=SCHEMA,
    )
    op.create_index("ix_system_configs_group", "system_configs", ["config_group"], schema=SCHEMA)

    op.create_table(
        "task_logs",
        id_column(),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence_no", sa.BigInteger(), nullable=False),
        sa.Column(
            "log_level",
            enum_type("debug", "info", "warning", "error", name="log_level"),
            nullable=False,
            server_default="info",
        ),
        sa.Column("log_type", sa.String(100), nullable=False),
        sa.Column("log_content", sa.Text(), nullable=False),
        created_at_column(),
        sa.UniqueConstraint("task_id", "sequence_no", name="uq_task_logs_task_sequence"),
        schema=SCHEMA,
    )
    op.create_index("ix_task_logs_task_id", "task_logs", ["task_id"], schema=SCHEMA)
    op.create_index(
        "ix_task_logs_task_created",
        "task_logs",
        ["task_id", "created_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("task_logs", schema=SCHEMA)
    op.drop_table("system_configs", schema=SCHEMA)
    op.drop_table("websocket_tokens", schema=SCHEMA)
    op.drop_table("context_summaries", schema=SCHEMA)
    op.drop_table("analysis_results", schema=SCHEMA)
    op.drop_table("analysis_tasks", schema=SCHEMA)
    op.drop_table("attachments", schema=SCHEMA)
    op.drop_table("messages", schema=SCHEMA)
    op.drop_table("conversations", schema=SCHEMA)
    op.drop_table("users", schema=SCHEMA)
