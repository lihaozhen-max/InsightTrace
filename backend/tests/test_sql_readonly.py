import os

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.errors import AppError
from app.db.session import engine
from app.tools import sql_readonly
from app.tools.sql_readonly import (
    ReadOnlySQLTool,
    RegisteredReadOnlyQuery,
    validate_registered_query,
)


def query(sql: str, *relations: str) -> RegisteredReadOnlyQuery:
    return RegisteredReadOnlyQuery(
        name="test_query",
        sql=sql,
        allowed_relations=frozenset(relations),
    )


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM demo_catalog.metrics",
        "SELECT * FROM demo_catalog.metrics; SELECT 1",
        "SELECT * INTO temporary_metrics FROM demo_catalog.metrics",
        "SELECT * FROM demo_catalog.metrics FOR UPDATE",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT * FROM unqualified_table",
        'SELECT * FROM "private"."secrets"',
    ],
)
def test_rejects_unsafe_sql(sql: str) -> None:
    with pytest.raises(AppError) as error:
        validate_registered_query(query(sql, "demo_catalog.metrics"))
    assert error.value.code == "SQL_REJECTED"


def test_accepts_parameterized_select_and_readonly_cte() -> None:
    registered = query(
        """
        WITH selected AS (
            SELECT category, conversion_rate
            FROM demo_catalog.daily_metrics
            WHERE metric_date >= :start_date
        )
        SELECT category, AVG(conversion_rate) AS average_rate
        FROM selected
        GROUP BY category
        """,
        "demo_catalog.daily_metrics",
    )
    assert validate_registered_query(registered).startswith("WITH selected")


@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run PostgreSQL readonly tool tests",
)
@pytest.mark.asyncio
async def test_executes_in_readonly_transaction_and_applies_row_limit() -> None:
    registered = query(
        """
        SELECT schemaname, tablename
        FROM pg_catalog.pg_tables
        ORDER BY schemaname, tablename
        """,
        "pg_catalog.pg_tables",
    )
    result = await ReadOnlySQLTool(engine, max_rows=2).execute(registered)
    assert result.columns == ["schemaname", "tablename"]
    assert result.row_count == 2
    assert result.truncated is True


@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run PostgreSQL readonly tool tests",
)
@pytest.mark.asyncio
async def test_readonly_transaction_blocks_mutation_even_after_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = ReadOnlySQLTool(engine)
    registered = query("SELECT 1", "pg_catalog.pg_tables")
    monkeypatch.setattr(
        sql_readonly,
        "validate_registered_query",
        lambda _: (
            "INSERT INTO insighttrace.system_configs "
            "(id, config_key, config_value, config_group) VALUES "
            "(gen_random_uuid(), 'unsafe', 'unsafe', 'unsafe') RETURNING config_key"
        ),
    )
    with pytest.raises(DBAPIError):
        await tool.execute(registered)


@pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run PostgreSQL readonly tool tests",
)
@pytest.mark.asyncio
async def test_statement_timeout_aborts_slow_query() -> None:
    slow_query = query("SELECT pg_sleep(0.1) AS delayed")
    with pytest.raises(DBAPIError):
        await ReadOnlySQLTool(engine, statement_timeout_ms=10).execute(slow_query)
