from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.analysis.deterministic import (
    change_rate,
    comparison_metric,
    point_map,
    ratio_metric,
    table_payload,
)
from app.schemas.analysis import AnalysisOutput
from app.tools.sql_readonly import ReadOnlySQLTool, RegisteredReadOnlyQuery

BEHAVIOR_QUERY = RegisteredReadOnlyQuery(
    name="customer_behavior_funnel_2026_08",
    sql="""
        SELECT period_start, channel, region, visitor_type, visits, product_views,
               add_to_carts, orders, suspicious_sessions, revenue
        FROM demo_behavior.funnel_metrics
        WHERE period_start >= :start_period AND period_start <= :end_period
        ORDER BY period_start, channel, region, visitor_type
    """,
    allowed_relations=frozenset({"demo_behavior.funnel_metrics"}),
)

_BEHAVIOR_KEYWORDS = frozenset(
    {"客户", "用户", "访客", "访问", "新客", "老客", "回访", "渠道", "地区", "流量"}
)


@dataclass(frozen=True)
class BehaviorAnalysisRun:
    output: AnalysisOutput
    rows_read: int
    metric_count: int


def is_behavior_question(question: str) -> bool:
    normalized = question.strip().lower()
    return any(keyword in normalized for keyword in _BEHAVIOR_KEYWORDS)


async def build_behavior_analysis(
    question: str,
    sql_tool: ReadOnlySQLTool,
    *,
    scenario_confirmed: bool = False,
) -> BehaviorAnalysisRun | None:
    if not scenario_confirmed and not is_behavior_question(question):
        return None

    query_result = await sql_tool.execute(
        BEHAVIOR_QUERY,
        {
            "start_period": date(2026, 8, 10),
            "end_period": date(2026, 8, 17),
        },
    )
    payload = table_payload(query_result.columns, query_result.rows)
    overall_orders = ratio_metric(
        payload,
        name="访问到下单转化率",
        numerator="orders",
        denominator="visits",
        group_by=["period_start"],
    )
    view_carts = ratio_metric(
        payload,
        name="商品浏览到加购率",
        numerator="add_to_carts",
        denominator="product_views",
        group_by=["period_start"],
    )
    cart_orders = ratio_metric(
        payload,
        name="加购到下单率",
        numerator="orders",
        denominator="add_to_carts",
        group_by=["period_start"],
    )
    channel_orders = ratio_metric(
        payload,
        name="渠道访问到下单转化率",
        numerator="orders",
        denominator="visits",
        group_by=["period_start", "channel"],
    )
    region_orders = ratio_metric(
        payload,
        name="地区访问到下单转化率",
        numerator="orders",
        denominator="visits",
        group_by=["period_start", "region"],
    )
    visitor_orders = ratio_metric(
        payload,
        name="访客类型访问到下单转化率",
        numerator="orders",
        denominator="visits",
        group_by=["period_start", "visitor_type"],
    )
    suspicious_rates = ratio_metric(
        payload,
        name="可疑会话占比",
        numerator="suspicious_sessions",
        denominator="visits",
        group_by=["period_start", "channel"],
    )

    previous = "2026-08-10"
    current = "2026-08-17"
    overall_map = point_map(overall_orders, "period_start")
    view_cart_map = point_map(view_carts, "period_start")
    cart_order_map = point_map(cart_orders, "period_start")
    channel_map = point_map(channel_orders, "period_start", "channel")
    region_map = point_map(region_orders, "period_start", "region")
    visitor_map = point_map(visitor_orders, "period_start", "visitor_type")
    suspicious_map = point_map(suspicious_rates, "period_start", "channel")

    previous_visits = sum(
        int(row["visits"])
        for row in query_result.rows
        if row["period_start"] == previous
    )
    current_visits = sum(
        int(row["visits"])
        for row in query_result.rows
        if row["period_start"] == current
    )
    previous_orders = sum(
        int(row["orders"])
        for row in query_result.rows
        if row["period_start"] == previous
    )
    current_orders = sum(
        int(row["orders"])
        for row in query_result.rows
        if row["period_start"] == current
    )
    previous_suspicious = sum(
        int(row["suspicious_sessions"])
        for row in query_result.rows
        if row["period_start"] == previous
    )
    current_suspicious = sum(
        int(row["suspicious_sessions"])
        for row in query_result.rows
        if row["period_start"] == current
    )
    overall_suspicious_previous = previous_suspicious / previous_visits * 100
    overall_suspicious_current = current_suspicious / current_visits * 100

    regions = sorted(key[1] for key in region_map if key[0] == current)
    worst_region = min(
        regions,
        key=lambda region: change_rate(
            region_map[(current, region)], region_map[(previous, region)]
        ),
    )
    visitor_types = sorted(key[1] for key in visitor_map if key[0] == current)
    worst_visitor_type = min(
        visitor_types,
        key=lambda visitor_type: change_rate(
            visitor_map[(current, visitor_type)],
            visitor_map[(previous, visitor_type)],
        ),
    )

    key_metrics = [
        comparison_metric(
            "访问到下单转化率",
            overall_map[(current,)],
            overall_map[(previous,)],
            current_period="2026-08-17 当周",
            comparison_period="2026-08-10 当周",
        ),
        comparison_metric(
            "商品浏览到加购率",
            view_cart_map[(current,)],
            view_cart_map[(previous,)],
            current_period="2026-08-17 当周",
            comparison_period="2026-08-10 当周",
        ),
        comparison_metric(
            "加购到下单率",
            cart_order_map[(current,)],
            cart_order_map[(previous,)],
            current_period="2026-08-17 当周",
            comparison_period="2026-08-10 当周",
        ),
        comparison_metric(
            "访问量",
            float(current_visits),
            float(previous_visits),
            current_period="2026-08-17 当周",
            comparison_period="2026-08-10 当周",
            unit="次",
        ),
        comparison_metric(
            "可疑会话占比",
            overall_suspicious_current,
            overall_suspicious_previous,
            current_period="2026-08-17 当周",
            comparison_period="2026-08-10 当周",
        ),
    ]
    evidence = [
        {
            "evidence_id": "E-001",
            "source_type": "database_query",
            "source_name": "demo_behavior.funnel_metrics",
            "evidence_text": (
                f"访问量由 {previous_visits:,} 增至 {current_visits:,}"
                f"（{change_rate(float(current_visits), float(previous_visits)):+.1f}%），"
                f"订单却由 {previous_orders:,} 降至 {current_orders:,}"
                f"（{change_rate(float(current_orders), float(previous_orders)):+.1f}%）。"
            ),
            "related_metric": "访问量与订单量",
            "confidence": 1.0,
            "fact_level": "observed",
        },
        {
            "evidence_id": "E-002",
            "source_type": "metric_calculation",
            "source_name": "渠道漏斗指标",
            "evidence_text": (
                "paid_social 渠道访问到下单转化率由 "
                f"{channel_map[(previous, 'paid_social')]:.2f}% 降至 "
                f"{channel_map[(current, 'paid_social')]:.2f}%；organic_search 同期由 "
                f"{channel_map[(previous, 'organic_search')]:.2f}% 变为 "
                f"{channel_map[(current, 'organic_search')]:.2f}%。"
            ),
            "related_metric": "渠道访问到下单转化率",
            "confidence": 0.98,
            "fact_level": "observed",
        },
        {
            "evidence_id": "E-003",
            "source_type": "metric_calculation",
            "source_name": "地区与访客分群指标",
            "evidence_text": (
                f"{worst_region}地区降幅最大；{worst_visitor_type}访客转化率由 "
                f"{visitor_map[(previous, worst_visitor_type)]:.2f}% 降至 "
                f"{visitor_map[(current, worst_visitor_type)]:.2f}%。"
            ),
            "related_metric": "地区与访客类型转化率",
            "confidence": 0.96,
            "fact_level": "observed",
        },
        {
            "evidence_id": "E-004",
            "source_type": "metric_calculation",
            "source_name": "可疑会话指标",
            "evidence_text": (
                f"可疑会话占比由 {overall_suspicious_previous:.2f}% 升至 "
                f"{overall_suspicious_current:.2f}%；本周 paid_social 渠道为 "
                f"{suspicious_map[(current, 'paid_social')]:.2f}%。"
            ),
            "related_metric": "可疑会话占比",
            "confidence": 0.95,
            "fact_level": "observed",
        },
    ]
    conclusion = (
        "本周访问量明显增加但订单减少，主要损耗来自 paid_social 渠道带来的新访客，"
        f"并在{worst_region}地区更集中。该渠道的可疑会话占比同步上升，说明新增流量"
        "质量需要核查；现有行为数据只能定位相关流量和漏斗损耗，不能直接认定为"
        "机器人流量、投放作弊或埋点故障。"
    )
    missing = (
        "缺少广告活动、投放素材、反作弊判定、设备指纹和埋点质量日志，暂时无法确认"
        "paid_social 新增流量质量下降的具体原因。"
    )
    next_actions = [
        f"按广告活动拆分 paid_social 在{worst_region}的新访客质量",
        "核对可疑会话的设备、访问频次和停留时长",
        "检查访问、浏览、加购和下单埋点在本周是否发生变更",
    ]
    metrics_markdown = "\n".join(
        f"- {item['metric_name']}：{item['metric_value']}{item['metric_unit']} "
        f"（上周：{item['comparison_value']}{item['metric_unit']}，"
        f"变化 {item['change_rate']:+.2f}%）"
        for item in key_metrics
    )
    evidence_markdown = "\n".join(
        f"- [{item['evidence_id']}] {item['evidence_text']}" for item in evidence
    )
    actions_markdown = "\n".join(f"- {item}" for item in next_actions)
    result_markdown = (
        f"# 客户行为归因分析\n\n## 1. 问题定义\n\n{question}\n\n"
        f"## 2. 关键指标\n\n{metrics_markdown}\n\n"
        f"## 3. 证据\n\n数据来源：`demo_behavior.funnel_metrics`\n\n"
        f"{evidence_markdown}\n\n"
        f"## 4. 结论\n\n{conclusion}\n\n"
        f"## 5. 缺失数据\n\n{missing}\n\n"
        f"## 6. 下一步建议\n\n{actions_markdown}"
    )
    return BehaviorAnalysisRun(
        output=AnalysisOutput(
            problem_definition=question,
            key_metrics=key_metrics,
            evidence_list=evidence,
            conclusion_text=conclusion,
            missing_data_text=missing,
            next_actions=next_actions,
            result_markdown=result_markdown,
            overall_confidence=0.91,
        ),
        rows_read=query_result.row_count,
        metric_count=7,
    )
