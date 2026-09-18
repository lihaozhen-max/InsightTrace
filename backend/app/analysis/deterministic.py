from __future__ import annotations

from app.schemas.tool import MetricCalculationResult, MetricDefinition
from app.tools.metrics import calculate_metric


def table_payload(
    columns: list[str],
    rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "kind": "table",
        "columns": columns,
        "row_count": len(rows),
        "rows": rows,
    }


def ratio_metric(
    payload: dict[str, object],
    *,
    name: str,
    numerator: str,
    denominator: str,
    group_by: list[str],
    filters: dict[str, str] | None = None,
) -> MetricCalculationResult:
    return calculate_metric(
        [payload],
        MetricDefinition(
            metric_name=name,
            operation="ratio",
            numerator_field=numerator,
            denominator_field=denominator,
            group_by=group_by,
            filters=filters or {},
            unit="%",
        ),
    )


def point_map(
    result: MetricCalculationResult,
    *dimensions: str,
) -> dict[tuple[str, ...], float]:
    return {
        tuple(point.dimensions[dimension] for dimension in dimensions): point.value
        for point in result.points
    }


def change_rate(current: float, previous: float) -> float:
    return (current - previous) / previous * 100 if previous else 0.0


def comparison_metric(
    name: str,
    current: float,
    previous: float,
    *,
    current_period: str,
    comparison_period: str,
    unit: str = "%",
) -> dict[str, object]:
    return {
        "metric_name": name,
        "metric_value": round(current, 2),
        "metric_unit": unit,
        "metric_period": current_period,
        "comparison_value": round(previous, 2),
        "comparison_period": comparison_period,
        "change_rate": round(change_rate(current, previous), 2),
    }
