from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import AppError
from app.schemas.tool import ReadOnlyQueryResult

_FORBIDDEN_KEYWORDS = frozenset(
    {
        "alter",
        "analyze",
        "call",
        "comment",
        "copy",
        "create",
        "delete",
        "do",
        "drop",
        "execute",
        "grant",
        "insert",
        "into",
        "listen",
        "load",
        "lock",
        "merge",
        "notify",
        "prepare",
        "refresh",
        "reindex",
        "reset",
        "revoke",
        "set",
        "truncate",
        "unlisten",
        "update",
        "vacuum",
    }
)
_FORBIDDEN_FUNCTIONS = frozenset(
    {
        "dblink",
        "lo_export",
        "lo_import",
        "pg_ls_dir",
        "pg_read_binary_file",
        "pg_read_file",
        "pg_stat_file",
        "pg_terminate_backend",
        "pg_write_file",
    }
)
_RELATION_PATTERN = re.compile(
    r"\b(?:from|join)\s+((?:[a-z_][a-z0-9_]*\.)?[a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)
_CTE_PATTERN = re.compile(r"(?:\bwith\b|,)\s*([a-z_][a-z0-9_]*)\s+as\s*\(", re.IGNORECASE)
_WORD_PATTERN = re.compile(r"[a-z_][a-z0-9_]*", re.IGNORECASE)


@dataclass(frozen=True)
class RegisteredReadOnlyQuery:
    name: str
    sql: str
    allowed_relations: frozenset[str]


def _sanitized_sql(sql: str) -> str:
    """Replace comments and quoted values before inspecting SQL structure."""

    output: list[str] = []
    index = 0
    state = "plain"
    while index < len(sql):
        current = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""
        if state == "plain":
            if current == "'":
                state = "single_quote"
                output.append(" ")
            elif current == '"':
                raise _rejected("查询模板暂不支持带引号的 SQL 标识符")
            elif current == "-" and following == "-":
                state = "line_comment"
                output.extend("  ")
                index += 1
            elif current == "/" and following == "*":
                state = "block_comment"
                output.extend("  ")
                index += 1
            else:
                output.append(current)
        elif state == "single_quote":
            output.append(" ")
            if current == "'" and following == "'":
                output.append(" ")
                index += 1
            elif current == "'":
                state = "plain"
        elif state == "line_comment":
            output.append("\n" if current == "\n" else " ")
            if current == "\n":
                state = "plain"
        else:
            output.append(" ")
            if current == "*" and following == "/":
                output.append(" ")
                index += 1
                state = "plain"
        index += 1
    if state in {"single_quote", "block_comment"}:
        raise _rejected("SQL 包含未闭合的引号或注释")
    return "".join(output)


def _rejected(message: str) -> AppError:
    return AppError(code="SQL_REJECTED", message=message, status_code=400)


def validate_registered_query(query: RegisteredReadOnlyQuery) -> str:
    sql = query.sql.strip()
    if not sql or "$" in sql:
        raise _rejected("查询为空或包含不支持的 SQL 引用语法")
    sanitized = _sanitized_sql(sql).strip()
    if sanitized.endswith(";"):
        sanitized = sanitized[:-1].rstrip()
        sql = sql[:-1].rstrip()
    if ";" in sanitized:
        raise _rejected("只允许执行一条 SQL 查询")

    words = [word.lower() for word in _WORD_PATTERN.findall(sanitized)]
    if not words or words[0] not in {"select", "with"}:
        raise _rejected("只允许 SELECT 或只读 CTE 查询")
    forbidden = sorted(set(words) & _FORBIDDEN_KEYWORDS)
    if forbidden:
        raise _rejected(f"查询包含禁止关键字：{', '.join(forbidden)}")
    lowered = sanitized.lower()
    if re.search(r"\bfor\s+(?:no\s+key\s+)?update\b|\bfor\s+share\b", lowered):
        raise _rejected("查询不能申请写锁")
    for function_name in _FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{re.escape(function_name)}\s*\(", lowered):
            raise _rejected("查询包含禁止的数据库函数")

    cte_names = {name.lower() for name in _CTE_PATTERN.findall(sanitized)}
    relations = {name.lower().replace('"', "") for name in _RELATION_PATTERN.findall(sanitized)}
    physical_relations = {name for name in relations if name not in cte_names}
    if any("." not in relation for relation in physical_relations):
        raise _rejected("数据表必须使用 schema.table 完整名称")
    allowed = {relation.lower() for relation in query.allowed_relations}
    unexpected = sorted(physical_relations - allowed)
    if unexpected:
        raise _rejected(f"查询访问了未授权数据表：{', '.join(unexpected)}")
    return sql


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime | date | time | UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


class ReadOnlySQLTool:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        statement_timeout_ms: int = 15_000,
        max_rows: int = 2_000,
    ) -> None:
        if statement_timeout_ms <= 0 or max_rows <= 0:
            raise ValueError("SQL timeout and row limit must be positive")
        self.engine = engine
        self.statement_timeout_ms = statement_timeout_ms
        self.max_rows = max_rows

    async def execute(
        self,
        query: RegisteredReadOnlyQuery,
        parameters: dict[str, Any] | None = None,
    ) -> ReadOnlyQueryResult:
        validated_sql = validate_registered_query(query)
        bound_parameters = dict(parameters or {})
        if "_insighttrace_row_limit" in bound_parameters:
            raise _rejected("查询参数名称与系统保留名称冲突")
        bound_parameters["_insighttrace_row_limit"] = self.max_rows + 1
        wrapped_sql = (
            "SELECT * FROM (\n"
            f"{validated_sql}\n"
            ") AS insighttrace_readonly_query "
            "LIMIT :_insighttrace_row_limit"
        )

        async with self.engine.connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            await connection.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": f"{self.statement_timeout_ms}ms"},
            )
            result = await connection.execute(text(wrapped_sql), bound_parameters)
            columns = list(result.keys())
            records = result.mappings().all()

        truncated = len(records) > self.max_rows
        visible_records = records[: self.max_rows]
        rows = [
            {column: _json_value(record[column]) for column in columns}
            for record in visible_records
        ]
        return ReadOnlyQueryResult(
            query_name=query.name,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
        )
