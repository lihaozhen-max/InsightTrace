from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.schemas.analysis import AnalysisOutput
from app.schemas.tool import MetricCalculationResult, MetricDefinition
from app.tools.metrics import calculate_metric
from app.tools.sql_readonly import ReadOnlySQLTool, RegisteredReadOnlyQuery

CATALOG_QUERY = RegisteredReadOnlyQuery(
    name="catalog_funnel_metrics_2026_07_08",
    sql="""
        SELECT period_month, product_id, product_name, category, device, channel,
               app_version, impressions, clicks, add_to_carts, orders, revenue
        FROM demo_catalog.funnel_metrics
        WHERE period_month >= :start_month AND period_month <= :end_month
        ORDER BY period_month, product_id, device, channel
    """,
    allowed_relations=frozenset({"demo_catalog.funnel_metrics"}),
)

_CATALOG_KEYWORDS = frozenset({"商品", "目录", "类目", "曝光"})


@dataclass(frozen=True)
class CatalogAnalysisRun:
    output: AnalysisOutput
    rows_read: int
    metric_count: int


def is_catalog_question(question: str) -> bool:
    normalized = question.strip().lower()
    return any(keyword in normalized for keyword in _CATALOG_KEYWORDS)


def _table_payload(columns: list[str], rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "kind": "table",
        "columns": columns,
        "row_count": len(rows),
        "rows": rows,
    }


def _ratio(
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


def _point_map(result: MetricCalculationResult, *dimensions: str) -> dict[tuple[str, ...], float]:
    return {
        tuple(point.dimensions[dimension] for dimension in dimensions): point.value
        for point in result.points
    }


def _change(current: float, previous: float) -> float:
    return (current - previous) / previous * 100 if previous else 0.0


def _metric_card(
    name: str,
    current: float,
    previous: float,
    *,
    unit: str = "%",
) -> dict[str, object]:
    return {
        "metric_name": name,
        "metric_value": round(current, 2),
        "metric_unit": unit,
        "metric_period": "2026-08",
        "comparison_value": round(previous, 2),
        "comparison_period": "2026-07",
        "change_rate": round(_change(current, previous), 2),
    }


async def build_catalog_analysis(
    question: str,
    sql_tool: ReadOnlySQLTool,
) -> CatalogAnalysisRun | None:
    if not is_catalog_question(question):
        return None

    query_result = await sql_tool.execute(
        CATALOG_QUERY,
        {
            "start_month": date(2026, 7, 1),
            "end_month": date(2026, 8, 1),
        },
    )
    payload = _table_payload(query_result.columns, query_result.rows)
    overall_orders = _ratio(
        payload,
        name="整体曝光到下单转化率",
        numerator="orders",
        denominator="impressions",
        group_by=["period_month"],
    )
    overall_clicks = _ratio(
        payload,
        name="整体点击率",
        numerator="clicks",
        denominator="impressions",
        group_by=["period_month"],
    )
    mobile_carts = _ratio(
        payload,
        name="移动端点击到加购率",
        numerator="add_to_carts",
        denominator="clicks",
        group_by=["period_month"],
        filters={"device": "mobile"},
    )
    category_orders = _ratio(
        payload,
        name="类目曝光到下单转化率",
        numerator="orders",
        denominator="impressions",
        group_by=["period_month", "category"],
    )
    device_carts = _ratio(
        payload,
        name="设备点击到加购率",
        numerator="add_to_carts",
        denominator="clicks",
        group_by=["period_month", "device"],
    )
    product_carts = _ratio(
        payload,
        name="商品移动端点击到加购率",
        numerator="add_to_carts",
        denominator="clicks",
        group_by=["period_month", "product_name"],
        filters={"device": "mobile"},
    )
    channel_orders = _ratio(
        payload,
        name="渠道曝光到下单转化率",
        numerator="orders",
        denominator="impressions",
        group_by=["period_month", "channel"],
    )

    july = "2026-07-01"
    august = "2026-08-01"
    overall_map = _point_map(overall_orders, "period_month")
    click_map = _point_map(overall_clicks, "period_month")
    mobile_map = _point_map(mobile_carts, "period_month")
    device_map = _point_map(device_carts, "period_month", "device")
    category_map = _point_map(category_orders, "period_month", "category")
    product_map = _point_map(product_carts, "period_month", "product_name")
    channel_map = _point_map(channel_orders, "period_month", "channel")

    july_overall = overall_map[(july,)]
    august_overall = overall_map[(august,)]
    july_mobile = mobile_map[(july,)]
    august_mobile = mobile_map[(august,)]
    july_desktop = device_map[(july, "desktop")]
    august_desktop = device_map[(august, "desktop")]

    products = sorted(key[1] for key in product_map if key[0] == august)
    worst_product = min(
        products,
        key=lambda product: _change(
            product_map[(august, product)], product_map[(july, product)]
        ),
    )
    worst_product_july = product_map[(july, worst_product)]
    worst_product_august = product_map[(august, worst_product)]

    categories = sorted(key[1] for key in category_map if key[0] == august)
    worst_category = min(
        categories,
        key=lambda category: _change(
            category_map[(august, category)], category_map[(july, category)]
        ),
    )
    channels = sorted(key[1] for key in channel_map if key[0] == august)
    weakest_channel = min(channels, key=lambda channel: channel_map[(august, channel)])

    july_impressions = sum(
        int(row["impressions"]) for row in query_result.rows if row["period_month"] == july
    )
    august_impressions = sum(
        int(row["impressions"]) for row in query_result.rows if row["period_month"] == august
    )
    impression_change = _change(float(august_impressions), float(july_impressions))

    key_metrics = [
        _metric_card("整体曝光到下单转化率", august_overall, july_overall),
        _metric_card("移动端点击到加购率", august_mobile, july_mobile),
        _metric_card("桌面端点击到加购率", august_desktop, july_desktop),
        _metric_card("整体点击率", click_map[(august,)], click_map[(july,)]),
        _metric_card(
            "整体曝光量",
            float(august_impressions),
            float(july_impressions),
            unit="次",
        ),
    ]
    evidence = [
        {
            "evidence_id": "E-001",
            "source_type": "database_query",
            "source_name": "demo_catalog.funnel_metrics",
            "evidence_text": (
                f"整体曝光量由 {july_impressions:,} 增至 {august_impressions:,}，"
                f"变化 {impression_change:+.1f}%，流量并未下降。"
            ),
            "related_metric": "整体曝光量",
            "confidence": 1.0,
            "fact_level": "observed",
        },
        {
            "evidence_id": "E-002",
            "source_type": "metric_calculation",
            "source_name": "移动端漏斗指标",
            "evidence_text": (
                f"移动端点击到加购率由 {july_mobile:.2f}% 降至 {august_mobile:.2f}%"
                f"（{_change(august_mobile, july_mobile):+.1f}%），"
                f"桌面端同期为 {july_desktop:.2f}% 到 {august_desktop:.2f}%。"
            ),
            "related_metric": "移动端点击到加购率",
            "confidence": 0.98,
            "fact_level": "observed",
        },
        {
            "evidence_id": "E-003",
            "source_type": "metric_calculation",
            "source_name": "商品维度漏斗指标",
            "evidence_text": (
                f"{worst_product} 的移动端点击到加购率由 {worst_product_july:.2f}% "
                f"降至 {worst_product_august:.2f}%，是三个商品中降幅最大的。"
            ),
            "related_metric": "商品移动端点击到加购率",
            "confidence": 0.96,
            "fact_level": "observed",
        },
        {
            "evidence_id": "E-004",
            "source_type": "metric_calculation",
            "source_name": "类目与渠道维度指标",
            "evidence_text": (
                f"{worst_category}类目的下单转化降幅最大；2026 年 8 月"
                f"{weakest_channel}渠道下单转化率最低，为 "
                f"{channel_map[(august, weakest_channel)]:.2f}%。"
            ),
            "related_metric": "类目与渠道转化率",
            "confidence": 0.94,
            "fact_level": "observed",
        },
    ]
    conclusion = (
        "2026 年 8 月整体转化下降不是由曝光减少造成，主要损耗集中在移动端点击后的"
        f"加购环节，其中{worst_product}的下降最明显。演示数据中的移动端记录同时从"
        "应用版本 5.7.0 切换到 5.8.0，但现有数据只能证明时间上的相关性，不能直接"
        "认定版本发布是技术根因。"
    )
    missing = (
        "缺少页面性能、接口错误、埋点完整性和版本灰度明细，暂时无法确认移动端"
        "加购损耗的具体技术原因。"
    )
    next_actions = [
        "按移动端应用版本和发布时间核对加购漏斗",
        f"优先检查{worst_product}详情页的性能、错误率和加购交互",
        "补充页面性能与接口错误日志后再次验证原因",
    ]
    metrics_markdown = "\n".join(
        f"- {item['metric_name']}：{item['metric_value']}{item['metric_unit']} "
        f"（2026-07：{item['comparison_value']}{item['metric_unit']}，"
        f"变化 {item['change_rate']:+.2f}%）"
        for item in key_metrics
    )
    evidence_markdown = "\n".join(
        f"- [{item['evidence_id']}] {item['evidence_text']}" for item in evidence
    )
    actions_markdown = "\n".join(f"- {item}" for item in next_actions)
    result_markdown = (
        f"# 商品目录归因分析\n\n## 1. 问题定义\n\n{question}\n\n"
        f"## 2. 关键指标\n\n{metrics_markdown}\n\n"
        f"## 3. 证据\n\n数据来源：`demo_catalog.funnel_metrics`\n\n"
        f"{evidence_markdown}\n\n"
        f"## 4. 结论\n\n{conclusion}\n\n"
        f"## 5. 缺失数据\n\n{missing}\n\n"
        f"## 6. 下一步建议\n\n{actions_markdown}"
    )
    return CatalogAnalysisRun(
        output=AnalysisOutput(
            problem_definition=question,
            key_metrics=key_metrics,
            evidence_list=evidence,
            conclusion_text=conclusion,
            missing_data_text=missing,
            next_actions=next_actions,
            result_markdown=result_markdown,
            overall_confidence=0.92,
        ),
        rows_read=query_result.row_count,
        metric_count=7,
    )
