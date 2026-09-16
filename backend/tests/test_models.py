from sqlalchemy.orm import configure_mappers

from app import models  # noqa: F401
from app.db.base import APP_SCHEMA, Base
from app.models.common import table_names

EXPECTED_TABLES = {
    "analysis_results",
    "analysis_tasks",
    "attachments",
    "context_summaries",
    "conversations",
    "messages",
    "system_configs",
    "task_logs",
    "users",
    "websocket_tokens",
}


def test_all_core_models_are_registered() -> None:
    configure_mappers()

    assert table_names(Base.metadata, APP_SCHEMA) == EXPECTED_TABLES


def test_active_task_partial_unique_index_is_declared() -> None:
    task_table = Base.metadata.tables[f"{APP_SCHEMA}.analysis_tasks"]
    indexes = {index.name: index for index in task_table.indexes}

    active_index = indexes["uq_analysis_tasks_active_conversation"]
    assert active_index.unique is True
    assert "task_status" in str(active_index.dialect_options["postgresql"]["where"])
