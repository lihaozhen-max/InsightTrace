from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.conversation import Attachment
from app.schemas.analysis import AnalysisOutput

PERIOD_ALIASES = ("月份", "日期", "month", "date", "period")
FUNNEL_ALIASES = {
    "exposure": ("曝光量", "展示量", "impressions", "exposures"),
    "click": ("点击量", "clicks", "click_count"),
    "cart": ("加购量", "carts", "add_to_cart", "cart_count"),
    "order": ("下单量", "订单量", "orders", "order_count"),
}
DIMENSION_ALIASES = {
    "product": ("商品名称", "product_name", "product"),
    "channel": ("渠道", "channel"),
    "device": ("设备", "device"),
    "region": ("地区", "region"),
    "category": ("类目", "category"),
}
STOCK_ALIASES = ("缺货率", "stockout_rate", "out_of_stock_rate")
ERROR_ALIASES = ("是否错误", "error", "is_error")
LOAD_TIME_ALIASES = ("页面加载毫秒", "load_time_ms", "page_load_ms")


@dataclass(frozen=True)
class SheetData:
    attachment_name: str
    name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    declared_rows: int


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


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {column.strip().lower(): column for column in columns}
    return next(
        (normalized[alias.lower()] for alias in aliases if alias.lower() in normalized),
        None,
    )


def _period(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"(20\d{2})[-/]?(\d{1,2})", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    return text


def _select_periods(question: str, available: list[str]) -> tuple[str, str]:
    years = {period[:4] for period in available if re.fullmatch(r"20\d{2}-\d{2}", period)}
    default_year = max(years, default="")
    requested: set[str] = set()
    for year, month in re.findall(r"(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月", question):
        if year or default_year:
            requested.add(f"{year or default_year}-{int(month):02d}")
    selected = sorted(requested.intersection(available))
    if len(selected) >= 2:
        return selected[-2], selected[-1]
    if len(selected) == 1:
        current_index = available.index(selected[0])
        if current_index > 0:
            return available[current_index - 1], selected[0]
    return available[-2], available[-1]


def _sheet_data(attachments: list[Attachment]) -> list[SheetData]:
    sheets: list[SheetData] = []
    for attachment in attachments:
        payload = attachment.parsed_content_json
        if not isinstance(payload, dict):
            continue
        raw_sheets = payload.get("sheets") if payload.get("kind") == "workbook" else [payload]
        if not isinstance(raw_sheets, list):
            continue
        for index, raw_sheet in enumerate(raw_sheets, start=1):
            if not isinstance(raw_sheet, dict):
                continue
            rows = [row for row in raw_sheet.get("rows", []) if isinstance(row, dict)]
            columns = [str(value) for value in raw_sheet.get("columns", [])]
            sheets.append(
                SheetData(
                    attachment_name=attachment.file_name,
                    name=str(raw_sheet.get("name") or f"sheet-{index}"),
                    columns=columns,
                    rows=rows,
                    declared_rows=int(raw_sheet.get("row_count") or len(rows)),
                )
            )
    return sheets


def _sum(rows: list[dict[str, Any]], field: str, period_field: str, period: str) -> Decimal:
    return sum(
        (
            number
            for row in rows
            if _period(row.get(period_field)) == period
            if (number := _decimal(row.get(field))) is not None
        ),
        Decimal(0),
    )


def _rate(numerator: Decimal, denominator: Decimal) -> Decimal:
    return numerator / denominator if denominator else Decimal(0)


def _rounded(value: Decimal, digits: int = 2) -> float:
    return round(float(value), digits)


def _metric(
    name: str,
    value: Decimal,
    unit: str,
    *,
    formula: str,
    source: SheetData,
    period: str | None = None,
) -> dict[str, Any]:
    return {
        "metric_name": name,
        "metric_value": _rounded(value),
        "metric_unit": unit,
        "metric_period": period,
        "formula": formula,
        "source_name": source.attachment_name,
        "sheet_name": source.name,
        "rows_used": len(source.rows),
        "fact_level": "calculation",
    }


def _dimension_changes(
    sheet: SheetData,
    *,
    period_field: str,
    value_field: str,
    dimension_field: str,
    previous_period: str,
    current_period: str,
) -> list[dict[str, Any]]:
    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for row in sheet.rows:
        period = _period(row.get(period_field))
        if period not in {previous_period, current_period}:
            continue
        value = _decimal(row.get(value_field))
        if value is None:
            continue
        totals[(str(row.get(dimension_field, "未知")), period)] += value
    total_delta = sum(
        (
            totals[(dimension, current_period)] - totals[(dimension, previous_period)]
            for dimension, period in totals
            if period == current_period
        ),
        Decimal(0),
    )
    changes: list[dict[str, Any]] = []
    dimensions = sorted({dimension for dimension, _ in totals})
    for dimension in dimensions:
        previous = totals[(dimension, previous_period)]
        current = totals[(dimension, current_period)]
        delta = current - previous
        share = delta / total_delta * 100 if total_delta and delta * total_delta > 0 else Decimal(0)
        changes.append(
            {
                "dimension": dimension,
                "previous": _rounded(previous),
                "current": _rounded(current),
                "delta": _rounded(delta),
                "contribution_percent": _rounded(share),
            }
        )
    return sorted(changes, key=lambda item: float(item["delta"]))


def _stockout_change(
    sheet: SheetData,
    *,
    period_field: str,
    product_field: str,
    stock_field: str,
    previous_period: str,
    current_period: str,
) -> dict[str, Any] | None:
    grouped: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    for row in sheet.rows:
        period = _period(row.get(period_field))
        value = _decimal(row.get(stock_field))
        if period in {previous_period, current_period} and value is not None:
            grouped[(str(row.get(product_field, "未知")), period)].append(value)
    candidates: list[dict[str, Any]] = []
    for product in {key[0] for key in grouped}:
        previous_values = grouped[(product, previous_period)]
        current_values = grouped[(product, current_period)]
        if not previous_values or not current_values:
            continue
        previous = sum(previous_values) / len(previous_values)
        current = sum(current_values) / len(current_values)
        candidates.append(
            {
                "product": product,
                "previous": _rounded(previous * 100),
                "current": _rounded(current * 100),
                "change_pp": _rounded((current - previous) * 100),
            }
        )
    return max(candidates, key=lambda item: float(item["change_pp"]), default=None)


def _anomaly_summary(
    sheets: list[SheetData],
    previous_period: str,
    current_period: str,
) -> dict[str, Any] | None:
    for sheet in sheets:
        period_field = _find_column(sheet.columns, PERIOD_ALIASES)
        error_field = _find_column(sheet.columns, ERROR_ALIASES)
        load_field = _find_column(sheet.columns, LOAD_TIME_ALIASES)
        if not period_field or not error_field:
            continue
        counts = {previous_period: 0, current_period: 0}
        errors = {previous_period: 0, current_period: 0}
        loads: dict[str, list[Decimal]] = defaultdict(list)
        combinations: dict[str, int] = defaultdict(int)
        product_field = _find_column(sheet.columns, DIMENSION_ALIASES["product"])
        channel_field = _find_column(sheet.columns, DIMENSION_ALIASES["channel"])
        device_field = _find_column(sheet.columns, DIMENSION_ALIASES["device"])
        for row in sheet.rows:
            period = _period(row.get(period_field))
            if period not in counts:
                continue
            counts[period] += 1
            is_error = str(row.get(error_field, "")).strip().lower() in {
                "是",
                "true",
                "1",
                "yes",
                "y",
            }
            if not is_error:
                continue
            errors[period] += 1
            load = _decimal(row.get(load_field)) if load_field else None
            if load is not None:
                loads[period].append(load)
            if period == current_period:
                parts = [
                    row.get(field)
                    for field in (product_field, channel_field, device_field)
                    if field
                ]
                combinations[" / ".join(str(value) for value in parts)] += 1
        if not any(counts.values()):
            continue
        top_combination = max(combinations.items(), key=lambda item: item[1], default=("无", 0))
        return {
            "sheet": sheet,
            "previous_count": counts[previous_period],
            "current_count": counts[current_period],
            "previous_errors": errors[previous_period],
            "current_errors": errors[current_period],
            "previous_rate": round(errors[previous_period] / counts[previous_period] * 100, 2)
            if counts[previous_period]
            else 0.0,
            "current_rate": round(errors[current_period] / counts[current_period] * 100, 2)
            if counts[current_period]
            else 0.0,
            "current_error_load_ms": round(
                float(sum(loads[current_period]) / len(loads[current_period])), 2
            )
            if loads[current_period]
            else None,
            "top_combination": top_combination[0],
            "top_combination_errors": top_combination[1],
        }
    return None


def _evidence(
    evidence_id: str,
    text: str,
    *,
    source: SheetData,
    level: str,
    formula: str | None = None,
    confidence: float = 1.0,
    sample_size: int | None = None,
    limitations: str | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_type": "attachment",
        "source_name": source.attachment_name,
        "sheet_name": source.name,
        "evidence_text": text,
        "fact_level": level,
        "formula": formula,
        "confidence": confidence,
        "sample_size": sample_size,
        "limitations": limitations,
    }


def _render_report(
    question: str,
    metrics: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    conclusion: str,
    missing: str,
    actions: list[str],
    *,
    scope: str,
) -> str:
    level_labels = {
        "observed": "已观察事实",
        "calculation": "确定性计算",
        "inference": "相关推断",
        "hypothesis": "待验证假设",
    }
    metric_rows = "\n".join(
        f"| {item['metric_name']} | {item['metric_value']}{item['metric_unit']} | "
        f"{item.get('metric_period') or '—'} | `{item['formula']}` |"
        for item in metrics
    )
    evidence_rows = "\n".join(
        f"{index}. **{level_labels.get(item['fact_level'], item['fact_level'])}** · "
        f"{item['evidence_text']} "
        f"\n   - 来源：{item['source_name']} / {item['sheet_name']}"
        + (f"\n   - 口径：`{item['formula']}`" if item.get("formula") else "")
        + (f"\n   - 限制：{item['limitations']}" if item.get("limitations") else "")
        for index, item in enumerate(evidence, start=1)
    )
    action_rows = "\n".join(f"- {action}" for action in actions)
    return (
        f"# 附件数据分析报告\n\n## 问题\n\n{question}\n\n"
        f"## 数据范围与方法\n\n{scope}\n\n"
        "指标由后端确定性计算；漏斗贡献采用对称分解，维度贡献采用对比期差值。\n\n"
        f"## 关键指标\n\n| 指标 | 数值 | 期间 | 计算口径 |\n|---|---:|---|---|\n{metric_rows}\n\n"
        f"## 证据链\n\n{evidence_rows}\n\n## 结论\n\n{conclusion}\n\n"
        f"## 数据限制\n\n{missing}\n\n## 下一步\n\n{action_rows}\n"
    )


def build_attachment_analysis(
    question: str,
    attachments: list[Attachment],
) -> AnalysisOutput | None:
    """Deterministically analyze a two-period funnel found in parsed attachments."""

    sheets = _sheet_data(attachments)
    funnel_sheet: SheetData | None = None
    fields: dict[str, str] = {}
    period_field = ""
    for sheet in sheets:
        candidate_period = _find_column(sheet.columns, PERIOD_ALIASES)
        candidate_fields = {
            name: column
            for name, aliases in FUNNEL_ALIASES.items()
            if (column := _find_column(sheet.columns, aliases))
        }
        if candidate_period and set(candidate_fields) == set(FUNNEL_ALIASES):
            funnel_sheet = sheet
            fields = candidate_fields
            period_field = candidate_period
            break
    if funnel_sheet is None:
        return None
    periods = sorted(
        {
            _period(row.get(period_field))
            for row in funnel_sheet.rows
            if row.get(period_field)
        }
    )
    if len(periods) < 2:
        return None
    previous_period, current_period = _select_periods(question, periods)
    totals = {
        period: {
            name: _sum(funnel_sheet.rows, field, period_field, period)
            for name, field in fields.items()
        }
        for period in (previous_period, current_period)
    }
    required_fields = [period_field, *fields.values()]
    invalid_rows = sum(
        1
        for row in funnel_sheet.rows
        if not row.get(period_field)
        or any(_decimal(row.get(field)) is None for field in fields.values())
    )
    rates = {
        period: {
            "order_click": _rate(values["order"], values["click"]),
            "click_cart": _rate(values["cart"], values["click"]),
            "cart_order": _rate(values["order"], values["cart"]),
            "click_exposure": _rate(values["click"], values["exposure"]),
        }
        for period, values in totals.items()
    }
    overall_delta = (
        rates[current_period]["order_click"] - rates[previous_period]["order_click"]
    ) * 100
    click_cart_contribution = (
        (rates[current_period]["click_cart"] - rates[previous_period]["click_cart"])
        * (rates[current_period]["cart_order"] + rates[previous_period]["cart_order"])
        / 2
        * 100
    )
    cart_order_contribution = (
        (rates[current_period]["cart_order"] - rates[previous_period]["cart_order"])
        * (rates[current_period]["click_cart"] + rates[previous_period]["click_cart"])
        / 2
        * 100
    )
    click_cart_share = (
        click_cart_contribution / overall_delta * 100 if overall_delta else Decimal(0)
    )
    cart_order_share = (
        cart_order_contribution / overall_delta * 100 if overall_delta else Decimal(0)
    )
    metrics = [
        _metric(
            f"{previous_period}整体下单转化率",
            rates[previous_period]["order_click"] * 100,
            "%",
            formula=f"SUM({fields['order']}) / SUM({fields['click']})",
            source=funnel_sheet,
            period=previous_period,
        ),
        _metric(
            f"{current_period}整体下单转化率",
            rates[current_period]["order_click"] * 100,
            "%",
            formula=f"SUM({fields['order']}) / SUM({fields['click']})",
            source=funnel_sheet,
            period=current_period,
        ),
        _metric(
            "整体下单转化率变化",
            overall_delta,
            "pp",
            formula=f"{current_period}转化率 - {previous_period}转化率",
            source=funnel_sheet,
        ),
        _metric(
            f"{current_period}点击→加购转化率",
            rates[current_period]["click_cart"] * 100,
            "%",
            formula=f"SUM({fields['cart']}) / SUM({fields['click']})",
            source=funnel_sheet,
            period=current_period,
        ),
        _metric(
            f"{current_period}加购→下单转化率",
            rates[current_period]["cart_order"] * 100,
            "%",
            formula=f"SUM({fields['order']}) / SUM({fields['cart']})",
            source=funnel_sheet,
            period=current_period,
        ),
        _metric(
            f"{current_period}点击率",
            rates[current_period]["click_exposure"] * 100,
            "%",
            formula=f"SUM({fields['click']}) / SUM({fields['exposure']})",
            source=funnel_sheet,
            period=current_period,
        ),
        _metric(
            "点击→加购贡献",
            click_cart_contribution,
            "pp",
            formula="Shapley((加购/点击) × (下单/加购))",
            source=funnel_sheet,
        ),
        _metric(
            "加购→下单贡献",
            cart_order_contribution,
            "pp",
            formula="Shapley((加购/点击) × (下单/加购))",
            source=funnel_sheet,
        ),
    ]
    metrics[3].update(
        comparison_value=_rounded(rates[previous_period]["click_cart"] * 100),
        comparison_period=previous_period,
    )
    metrics[4].update(
        comparison_value=_rounded(rates[previous_period]["cart_order"] * 100),
        comparison_period=previous_period,
    )
    metrics[5].update(
        comparison_value=_rounded(rates[previous_period]["click_exposure"] * 100),
        comparison_period=previous_period,
    )
    evidence = [
        _evidence(
            "E-001",
            f"{previous_period}下单/点击为"
            f"{_rounded(rates[previous_period]['order_click'] * 100)}%，"
            f"{current_period}为{_rounded(rates[current_period]['order_click'] * 100)}%，"
            f"变化{_rounded(overall_delta)}个百分点。",
            source=funnel_sheet,
            level="calculation",
            formula=f"SUM({fields['order']}) / SUM({fields['click']})",
            sample_size=len(funnel_sheet.rows),
        ),
        _evidence(
            "E-002",
            f"对称分解显示：点击→加购贡献{_rounded(click_cart_contribution)}pp"
            f"（约{_rounded(click_cart_share, 1)}%），加购→下单贡献"
            f"{_rounded(cart_order_contribution)}pp（约{_rounded(cart_order_share, 1)}%）。",
            source=funnel_sheet,
            level="calculation",
            formula="two-factor Shapley decomposition",
            sample_size=len(funnel_sheet.rows),
        ),
        _evidence(
            "E-003",
            f"漏斗表共{len(funnel_sheet.rows)}行，核心字段缺失或非数字行为"
            f"{invalid_rows}行；计算字段为{'、'.join(required_fields)}。",
            source=funnel_sheet,
            level="observed",
            sample_size=len(funnel_sheet.rows),
            limitations="无效数值在对应指标汇总时会被跳过。" if invalid_rows else None,
        ),
    ]
    dimension_fields = {
        name: column
        for name, aliases in DIMENSION_ALIASES.items()
        if (column := _find_column(funnel_sheet.columns, aliases))
    }
    top_product: dict[str, Any] | None = None
    for dimension_name, dimension_field in dimension_fields.items():
        changes = _dimension_changes(
            funnel_sheet,
            period_field=period_field,
            value_field=fields["order"],
            dimension_field=dimension_field,
            previous_period=previous_period,
            current_period=current_period,
        )
        top_change = changes[0] if changes else None
        if dimension_name == "product":
            top_product = top_change
        if top_change:
            evidence.append(
                _evidence(
                    f"E-{len(evidence) + 1:03d}",
                    f"{dimension_field}贡献排名中，{top_change['dimension']}下单量从"
                    f"{top_change['previous']}变为{top_change['current']}，变化"
                    f"{top_change['delta']}单，对同向整体变化的贡献为"
                    f"{top_change['contribution_percent']}%。",
                    source=funnel_sheet,
                    level="calculation",
                    formula=f"SUM({fields['order']}) BY {dimension_field}",
                    sample_size=len(funnel_sheet.rows),
                )
            )
    stock_field = _find_column(funnel_sheet.columns, STOCK_ALIASES)
    stock_change = None
    if product_field := dimension_fields.get("product"):
        if stock_field:
            stock_change = _stockout_change(
                funnel_sheet,
                period_field=period_field,
                product_field=product_field,
                stock_field=stock_field,
                previous_period=previous_period,
                current_period=current_period,
            )
    if stock_change and float(stock_change["change_pp"]) > 0:
        evidence.append(
            _evidence(
                f"E-{len(evidence) + 1:03d}",
                f"{stock_change['product']}缺货率从{stock_change['previous']}%升至"
                f"{stock_change['current']}%，上升{stock_change['change_pp']}pp；"
                "这是相关线索，不单独构成因果证明。",
                source=funnel_sheet,
                level="inference",
                formula=f"AVG({stock_field}) BY {product_field}",
                confidence=0.78,
                sample_size=len(funnel_sheet.rows),
                limitations="缺少库存日志和补货时间，仅能判定同期变化。",
            )
        )
    anomaly = _anomaly_summary(sheets, previous_period, current_period)
    if anomaly:
        evidence.append(
            _evidence(
                f"E-{len(evidence) + 1:03d}",
                f"抽样订单明细中，{previous_period}错误率为{anomaly['previous_rate']}%"
                f"（{anomaly['previous_errors']}/{anomaly['previous_count']}），{current_period}为"
                f"{anomaly['current_rate']}%（{anomaly['current_errors']}/{anomaly['current_count']}）；"
                f"当期错误最集中组合为{anomaly['top_combination']}。",
                source=anomaly["sheet"],
                level="observed",
                formula="错误记录数 / 抽样订单数",
                confidence=0.75,
                sample_size=anomaly["previous_count"] + anomaly["current_count"],
                limitations="订单明细为抽样数据，不能直接外推为全量订单错误率。",
            )
        )
    leading_stage = (
        "点击→加购"
        if abs(click_cart_contribution) >= abs(cart_order_contribution)
        else "加购→下单"
    )
    leading_share = max(abs(click_cart_share), abs(cart_order_share))
    conclusion_parts = [
        f"{current_period}整体下单转化率较{previous_period}变化{_rounded(overall_delta)}个百分点。",
        f"确定性分解表明，下降主要发生在{leading_stage}环节，约贡献"
        f"{_rounded(leading_share, 1)}%的总降幅。",
    ]
    if top_product:
        conclusion_parts.append(
            f"{top_product['dimension']}是商品维度的最大下降项，但其相关异常仍需通过全量日志验证因果。"
        )
    conclusion = "".join(conclusion_parts)
    total_rows = sum(sheet.declared_rows for sheet in sheets)
    scope = (
        f"已分析 {len(attachments)} 个附件、{len(sheets)} 个工作表，共 {total_rows} 行；"
        f"对比期为 {previous_period} 与 {current_period}。"
    )
    missing = (
        "附件缺少促销、价格、竞品、全量库存与发布日志；订单明细为抽样数据。"
        "因此可以确认指标变化与贡献度，但不能将缺货或页面错误直接定性为唯一原因。"
    )
    if invalid_rows:
        missing += f"漏斗表有{invalid_rows}行核心字段无效，对应值已跳过。"
    actions = [
        "P0（数据分析/运营）：按商品×渠道×设备复核下降贡献，以转化率恢复幅度为验收指标。",
        "P0（供应链）：核对最大下降商品的库存与补货日志，对比缺货和正常时段转化率。",
        "P1（前端研发/SRE）：用全量监控和订单日志验证错误率、加载时间与转化的关联。",
        "P1（运营）：补充促销、价格和流量结构数据，对已发现线索进行因果验证。",
    ]
    report = _render_report(
        question,
        metrics,
        evidence,
        conclusion,
        missing,
        actions,
        scope=scope,
    )
    return AnalysisOutput(
        problem_definition=question,
        key_metrics=metrics,
        evidence_list=evidence,
        conclusion_text=conclusion,
        missing_data_text=missing,
        next_actions=actions,
        result_markdown=report,
        overall_confidence=0.9 if anomaly and top_product else 0.82,
    )
