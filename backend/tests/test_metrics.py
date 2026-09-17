import pytest

from app.core.errors import AppError
from app.schemas.tool import MetricDefinition
from app.tools.metrics import calculate_metric

PAYLOAD = {
    "kind": "table",
    "rows": [
        {"渠道": "自然", "访问": 100, "下单": 10, "收入": "1,200.5"},
        {"渠道": "自然", "访问": 50, "下单": 4, "收入": "无效"},
        {"渠道": "广告", "访问": 80, "下单": 4, "收入": 800},
    ],
}


def test_calculates_grouped_sum_and_tracks_invalid_rows() -> None:
    result = calculate_metric(
        [PAYLOAD],
        MetricDefinition(
            metric_name="渠道收入",
            operation="sum",
            value_field="收入",
            group_by=["渠道"],
            unit="元",
        ),
    )
    assert [(point.dimensions, point.value) for point in result.points] == [
        ({"渠道": "广告"}, 800.0),
        ({"渠道": "自然"}, 1200.5),
    ]
    assert result.points[1].rows_skipped == 1


def test_calculates_ratio_from_aggregated_fields() -> None:
    result = calculate_metric(
        [PAYLOAD],
        MetricDefinition(
            metric_name="渠道转化率",
            operation="ratio",
            numerator_field="下单",
            denominator_field="访问",
            group_by=["渠道"],
            unit="%",
        ),
    )
    assert result.points[0].value == 5.0
    assert result.points[1].value == pytest.approx(9.3333333333)


def test_filters_and_counts_rows() -> None:
    result = calculate_metric(
        [PAYLOAD],
        MetricDefinition(
            metric_name="自然渠道记录数",
            operation="count",
            filters={"渠道": "自然"},
        ),
    )
    assert result.points[0].value == 2
    assert result.matched_rows == 2


def test_rejects_missing_fields_and_zero_denominator() -> None:
    with pytest.raises(AppError) as missing:
        calculate_metric(
            [PAYLOAD],
            MetricDefinition(metric_name="缺失", operation="sum", value_field="成本"),
        )
    assert missing.value.code == "METRIC_FIELD_MISSING"

    with pytest.raises(AppError) as zero:
        calculate_metric(
            [{"kind": "table", "rows": [{"点击": 1, "曝光": 0}]}],
            MetricDefinition(
                metric_name="点击率",
                operation="ratio",
                numerator_field="点击",
                denominator_field="曝光",
            ),
        )
    assert zero.value.code == "METRIC_ZERO_DENOMINATOR"
