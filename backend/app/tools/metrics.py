from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.errors import AppError
from app.schemas.tool import MetricCalculationResult, MetricDefinition, MetricPoint
from app.tools.attachment_content import iter_tabular_rows


def _metric_error(code: str, message: str) -> AppError:
    return AppError(code=code, message=message, status_code=422)


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    normalized = str(value).strip().replace(",", "")
    if normalized.endswith("%"):
        normalized = normalized[:-1]
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _matches_filters(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    return all(row.get(field) == expected for field, expected in filters.items())


def _required_fields(definition: MetricDefinition) -> set[str]:
    fields = {*definition.group_by, *definition.filters}
    if definition.operation in {"sum", "average", "minimum", "maximum"}:
        if not definition.value_field:
            raise _metric_error("METRIC_FIELD_REQUIRED", "该指标操作必须指定 value_field")
        fields.add(definition.value_field)
    elif definition.operation == "ratio":
        if not definition.numerator_field or not definition.denominator_field:
            raise _metric_error(
                "METRIC_RATIO_FIELDS_REQUIRED",
                "比率指标必须指定 numerator_field 和 denominator_field",
            )
        fields.update((definition.numerator_field, definition.denominator_field))
    return fields


def calculate_metric(
    payloads: list[dict[str, Any]],
    definition: MetricDefinition,
    *,
    max_rows: int = 100_000,
    max_groups: int = 200,
) -> MetricCalculationResult:
    required = _required_fields(definition)
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        for _, row in iter_tabular_rows(payload):
            if len(rows) >= max_rows:
                raise _metric_error("METRIC_ROW_LIMIT", "参与指标计算的数据行超过安全上限")
            rows.append(row)
    if not rows:
        raise _metric_error("METRIC_DATA_EMPTY", "没有可用于指标计算的表格数据")
    available = set().union(*(row.keys() for row in rows))
    missing = sorted(required - available)
    if missing:
        raise _metric_error("METRIC_FIELD_MISSING", f"数据缺少字段：{', '.join(missing)}")

    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    matched_rows = 0
    for row in rows:
        if not _matches_filters(row, definition.filters):
            continue
        matched_rows += 1
        key = tuple(str(row.get(field, "")) for field in definition.group_by)
        grouped[key].append(row)
        if len(grouped) > max_groups:
            raise _metric_error("METRIC_GROUP_LIMIT", "指标分组数量超过安全上限")

    points: list[MetricPoint] = []
    for key, group_rows in sorted(grouped.items()):
        skipped = 0
        used = 0
        value: Decimal
        if definition.operation == "count":
            value = Decimal(len(group_rows))
            used = len(group_rows)
        elif definition.operation == "ratio":
            numerator = Decimal(0)
            denominator = Decimal(0)
            for row in group_rows:
                numerator_value = _decimal(row.get(definition.numerator_field or ""))
                denominator_value = _decimal(row.get(definition.denominator_field or ""))
                if numerator_value is None or denominator_value is None:
                    skipped += 1
                    continue
                numerator += numerator_value
                denominator += denominator_value
                used += 1
            if denominator == 0:
                raise _metric_error("METRIC_ZERO_DENOMINATOR", "比率指标的分母合计为零")
            value = numerator / denominator * Decimal(str(definition.ratio_scale))
        else:
            values: list[Decimal] = []
            for row in group_rows:
                parsed = _decimal(row.get(definition.value_field or ""))
                if parsed is None:
                    skipped += 1
                else:
                    values.append(parsed)
            if not values:
                continue
            used = len(values)
            if definition.operation == "sum":
                value = sum(values, Decimal(0))
            elif definition.operation == "average":
                value = sum(values, Decimal(0)) / Decimal(len(values))
            elif definition.operation == "minimum":
                value = min(values)
            else:
                value = max(values)
        points.append(
            MetricPoint(
                dimensions=dict(zip(definition.group_by, key, strict=True)),
                value=float(value),
                unit=definition.unit,
                rows_used=used,
                rows_skipped=skipped,
            )
        )
    if not points:
        raise _metric_error("METRIC_NO_MATCH", "没有符合筛选条件的有效数据")
    return MetricCalculationResult(
        metric_name=definition.metric_name,
        operation=definition.operation,
        points=points,
        total_rows=len(rows),
        matched_rows=matched_rows,
    )
