from app.analysis.attachment import build_attachment_analysis
from app.analysis.audit import audit_metadata, audit_model_output, reconcile_model_output
from app.models.conversation import Attachment
from app.schemas.analysis import AnalysisOutput


def _attachment() -> Attachment:
    return Attachment(
        file_name="funnel.xlsx",
        parsed_content_json={
            "kind": "workbook",
            "row_count": 8,
            "sheets": [
                {
                    "name": "商品漏斗",
                    "columns": [
                        "月份",
                        "商品名称",
                        "曝光量",
                        "点击量",
                        "加购量",
                        "下单量",
                        "缺货率",
                    ],
                    "row_count": 4,
                    "rows": [
                        {
                            "月份": "2026-07",
                            "商品名称": "A",
                            "曝光量": 1000,
                            "点击量": 100,
                            "加购量": 20,
                            "下单量": 10,
                            "缺货率": 0.01,
                        },
                        {
                            "月份": "2026-07",
                            "商品名称": "B",
                            "曝光量": 1000,
                            "点击量": 100,
                            "加购量": 20,
                            "下单量": 10,
                            "缺货率": 0.01,
                        },
                        {
                            "月份": "2026-08",
                            "商品名称": "A",
                            "曝光量": 1000,
                            "点击量": 120,
                            "加购量": 12,
                            "下单量": 4,
                            "缺货率": 0.08,
                        },
                        {
                            "月份": "2026-08",
                            "商品名称": "B",
                            "曝光量": 1000,
                            "点击量": 120,
                            "加购量": 24,
                            "下单量": 12,
                            "缺货率": 0.01,
                        },
                    ],
                },
                {
                    "name": "订单明细",
                    "columns": ["日期", "商品名称", "渠道", "设备", "是否错误", "页面加载毫秒"],
                    "row_count": 4,
                    "rows": [
                        {
                            "日期": "2026-07-01",
                            "商品名称": "A",
                            "渠道": "organic",
                            "设备": "mobile",
                            "是否错误": "否",
                            "页面加载毫秒": 1000,
                        },
                        {
                            "日期": "2026-07-02",
                            "商品名称": "B",
                            "渠道": "organic",
                            "设备": "desktop",
                            "是否错误": "否",
                            "页面加载毫秒": 1100,
                        },
                        {
                            "日期": "2026-08-01",
                            "商品名称": "A",
                            "渠道": "paid",
                            "设备": "mobile",
                            "是否错误": "是",
                            "页面加载毫秒": 4200,
                        },
                        {
                            "日期": "2026-08-02",
                            "商品名称": "B",
                            "渠道": "organic",
                            "设备": "desktop",
                            "是否错误": "否",
                            "页面加载毫秒": 1200,
                        },
                    ],
                },
            ],
        },
    )


def test_builds_deterministic_funnel_attribution_and_evidence_levels() -> None:
    output = build_attachment_analysis("分析8月为什么下降", [_attachment()])

    assert output is not None
    values = {item["metric_name"]: item["metric_value"] for item in output.key_metrics}
    assert values["2026-07整体下单转化率"] == 10.0
    assert values["2026-08整体下单转化率"] == 6.67
    assert values["整体下单转化率变化"] == -3.33
    assert values["点击→加购贡献"] == -2.36
    assert values["加购→下单贡献"] == -0.97
    assert "A下单量从10.0变为4.0" in output.result_markdown
    assert "抽样订单明细中" in output.result_markdown
    assert {item["fact_level"] for item in output.evidence_list} >= {
        "calculation",
        "inference",
        "observed",
    }


def test_report_auditor_rejects_unsupported_causal_claims() -> None:
    grounding = build_attachment_analysis("分析8月为什么下降", [_attachment()])
    assert grounding is not None
    generated = AnalysisOutput(
        problem_definition=grounding.problem_definition,
        key_metrics=grounding.key_metrics,
        evidence_list=grounding.evidence_list,
        conclusion_text="页面错误已经证明是唯一原因，造成99%的下降。",
        missing_data_text="",
        next_actions=[],
        result_markdown="页面错误已经证明是唯一原因。",
        overall_confidence=1.0,
    )

    audit = audit_model_output(generated, grounding)
    reconciled = reconcile_model_output(generated, grounding)

    assert audit.accepted is False
    assert reconciled.conclusion_text == grounding.conclusion_text
    assert reconciled.key_metrics == grounding.key_metrics
    assert reconciled.evidence_list[-1]["model_output_accepted"] is False
    assert "已回退为确定性结论" in reconciled.result_markdown


def test_report_auditor_accepts_grounded_narrative() -> None:
    grounding = build_attachment_analysis("分析8月为什么下降", [_attachment()])
    assert grounding is not None
    generated = grounding.model_copy(
        update={
            "conclusion_text": grounding.conclusion_text,
            "result_markdown": grounding.result_markdown,
        }
    )

    audit = audit_model_output(generated, grounding)
    reconciled = reconcile_model_output(generated, grounding)

    assert audit.accepted is True
    assert reconciled.evidence_list[-1]["model_output_accepted"] is True
    assert "已通过数值溯源" in reconciled.result_markdown
    assert audit_metadata(reconciled)["model_output_accepted"] is True


def test_report_auditor_allows_explicitly_negated_causal_phrase() -> None:
    grounding = build_attachment_analysis("分析8月为什么下降", [_attachment()])
    assert grounding is not None
    generated = grounding.model_copy(
        update={
            "conclusion_text": "现有证据不足，不能认为完全由抽样数据中的页面错误造成。",
            "result_markdown": "现有证据不足，不能认为完全由抽样数据中的页面错误造成。",
        }
    )

    assert audit_model_output(generated, grounding).accepted is True


def test_dimension_contribution_includes_values_missing_from_current_period() -> None:
    attachment = Attachment(
        file_name="disappearing-product.xlsx",
        parsed_content_json={
            "kind": "table",
            "name": "漏斗",
            "columns": ["月份", "商品名称", "曝光量", "点击量", "加购量", "下单量"],
            "rows": [
                {
                    "月份": "2026-07",
                    "商品名称": "A",
                    "曝光量": 1000,
                    "点击量": 100,
                    "加购量": 20,
                    "下单量": 10,
                },
                {
                    "月份": "2026-07",
                    "商品名称": "B",
                    "曝光量": 1000,
                    "点击量": 100,
                    "加购量": 20,
                    "下单量": 10,
                },
                {
                    "月份": "2026-08",
                    "商品名称": "A",
                    "曝光量": 1000,
                    "点击量": 100,
                    "加购量": 20,
                    "下单量": 10,
                },
            ],
        },
    )

    output = build_attachment_analysis("分析8月商品变化", [attachment])

    assert output is not None
    product_evidence = next(
        item for item in output.evidence_list if "商品名称贡献排名" in item["evidence_text"]
    )
    assert "B下单量从10.0变为0.0" in product_evidence["evidence_text"]
    assert "贡献为100.0%" in product_evidence["evidence_text"]
