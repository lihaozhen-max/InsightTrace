import os

import pytest
from sqlalchemy import inspect, text

from app.db.base import APP_SCHEMA
from app.db.session import engine
from tests.test_models import EXPECTED_TABLES

pytestmark = [
    pytest.mark.skipif(
        os.getenv("RUN_DB_TESTS") != "1",
        reason="Set RUN_DB_TESTS=1 to run PostgreSQL schema checks",
    ),
    pytest.mark.asyncio(loop_scope="module"),
]


async def test_migration_created_expected_tables() -> None:
    async with engine.connect() as connection:
        tables = await connection.run_sync(
            lambda sync_connection: set(
                inspect(sync_connection).get_table_names(schema=APP_SCHEMA)
            )
        )

    assert tables - {"alembic_version"} == EXPECTED_TABLES


async def test_only_one_active_task_is_allowed_per_conversation() -> None:
    async with engine.connect() as connection:
        index_definition = await connection.scalar(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE schemaname = :schema_name
                  AND indexname = 'uq_analysis_tasks_active_conversation'
                """
            ),
            {"schema_name": APP_SCHEMA},
        )

    assert index_definition is not None
    assert "UNIQUE" in index_definition
    assert "queued" in index_definition
    assert "running" in index_definition
