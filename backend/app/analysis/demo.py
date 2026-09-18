from __future__ import annotations

from typing import Any

from app.models.conversation import Attachment
from app.schemas.analysis import AnalysisOutput


def _attachment_size(payload: dict[str, Any] | list[Any] | None) -> tuple[int, int]:
    if not isinstance(payload, dict):
        return 0, 0
    if payload.get("kind") == "table":
        return int(payload.get("row_count", 0)), len(payload.get("columns", []))
    if payload.get("kind") == "workbook":
        sheets = payload.get("sheets", [])
        max_columns = max(
            (len(sheet.get("columns", [])) for sheet in sheets if isinstance(sheet, dict)),
            default=0,
        )
        return int(payload.get("row_count", 0)), max_columns
    if payload.get("kind") == "json":
        data = payload.get("data")
        return len(data) if isinstance(data, list) else int(data is not None), 0
    return 0, 0


def build_demo_analysis(question: str, attachments: list[Attachment]) -> AnalysisOutput:
    """Build a deterministic M3 result without pretending to perform M4 attribution."""

    source_summaries: list[str] = []
    total_rows = 0
    max_columns = 0
    for attachment in attachments:
        rows, columns = _attachment_size(attachment.parsed_content_json)
        total_rows += rows
        max_columns = max(max_columns, columns)
        source_summaries.append(f"{attachment.file_name}（{rows} 行，最多 {columns} 列）")

    source_count = len(attachments)
    key_metrics = [
        {"metric_name": "已读取数据源", "metric_value": source_count, "metric_unit": "个"},
        {"metric_name": "可检查记录", "metric_value": total_rows, "metric_unit": "行"},
    ]
    if source_count:
        evidence = [
            {
                "evidence_id": f"E-{index:03d}",
                "source_type": "attachment",
                "source_name": attachment.file_name,
                "evidence_text": summary,
                "fact_level": "observed",
            }
            for index, (attachment, summary) in enumerate(
                zip(attachments, source_summaries, strict=True), start=1
            )
        ]
        conclusion = (
            f"任务执行链路已完成，并成功检查 {source_count} 个附件、{total_rows} 行记录。"
            "M3 只验证任务编排与结果交付，经营归因结论将在 M4 接入指标工具后生成。"
        )
        missing = "尚未接入 M4 的只读 SQL、指标计算和归因规则，当前不能给出可靠的经营原因判断。"
        confidence = 0.6
    else:
        evidence = [
            {
                "evidence_id": "E-001",
                "source_type": "task_input",
                "source_name": "当前问题",
                "evidence_text": "本轮没有选择可供计算的附件。",
                "fact_level": "observed",
            }
        ]
        conclusion = "任务执行链路已完成，但没有数据源，暂时不能形成数据驱动的经营归因结论。"
        missing = "请上传 CSV、XLSX、JSON 或 TXT 数据，并在后续分析任务中选择相应附件。"
        confidence = 0.3

    next_actions = [
        "确认分析所需的指标口径和时间范围",
        "在 M4 接入只读数据查询与指标计算工具",
    ]
    sources_markdown = "\n".join(f"- {item}" for item in source_summaries) or "- 未选择附件"
    metrics_markdown = "\n".join(
        f"- {item['metric_name']}：{item['metric_value']}{item['metric_unit']}"
        for item in key_metrics
    )
    actions_markdown = "\n".join(f"- {item}" for item in next_actions)
    result_markdown = (
        f"# 分析执行结果\n\n## 问题\n\n{question}\n\n"
        f"## 数据概览\n\n{metrics_markdown}\n\n## 数据来源\n\n{sources_markdown}\n\n"
        f"## 当前结论\n\n{conclusion}\n\n## 缺失信息\n\n{missing}\n\n"
        f"## 下一步\n\n{actions_markdown}"
    )
    return AnalysisOutput(
        problem_definition=question,
        key_metrics=key_metrics,
        evidence_list=evidence,
        conclusion_text=conclusion,
        missing_data_text=missing,
        next_actions=next_actions,
        result_markdown=result_markdown,
        overall_confidence=confidence,
    )


def build_attachment_grounding(
    question: str,
    attachments: list[Attachment],
) -> AnalysisOutput:
    """Build factual attachment metadata before model-based analysis."""

    source_summaries: list[str] = []
    evidence: list[dict[str, Any]] = []
    total_rows = 0
    for index, attachment in enumerate(attachments, start=1):
        rows, columns = _attachment_size(attachment.parsed_content_json)
        total_rows += rows
        summary = f"{attachment.file_name}：已解析 {rows} 行，最多 {columns} 列"
        source_summaries.append(summary)
        evidence.append(
            {
                "evidence_id": f"E-{index:03d}",
                "source_type": "attachment",
                "source_name": attachment.file_name,
                "evidence_text": summary,
                "fact_level": "observed",
            }
        )
    key_metrics = [
        {"metric_name": "已读取数据源", "metric_value": len(attachments), "metric_unit": "个"},
        {"metric_name": "已解析记录", "metric_value": total_rows, "metric_unit": "行"},
    ]
    conclusion = (
        f"已读取 {len(attachments)} 个附件、{total_rows} 行记录。"
        "附件的受控数据摘录将交给模型进行指标比较和归因分析。"
    )
    next_actions = ["核对模型引用的字段和数值", "根据首轮结论继续下钻维度"]
    result_markdown = (
        f"# 附件分析准备结果\n\n## 问题\n\n{question}\n\n"
        f"## 数据来源\n\n- " + "\n- ".join(source_summaries) + "\n\n"
        f"## 当前状态\n\n{conclusion}"
    )
    return AnalysisOutput(
        problem_definition=question,
        key_metrics=key_metrics,
        evidence_list=evidence,
        conclusion_text=conclusion,
        missing_data_text="模型必须仅依据附件摘录作答；被截断的数据需要在结论中说明。",
        next_actions=next_actions,
        result_markdown=result_markdown,
        overall_confidence=0.7,
    )
