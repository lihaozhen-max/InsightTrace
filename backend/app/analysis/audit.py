from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.analysis import AnalysisOutput

PROHIBITED_CAUSAL_PHRASES = ("必然导致", "已经证明", "完全由")
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class AuditResult:
    accepted: bool
    findings: tuple[str, ...]


def _numbers(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for token in NUMBER_PATTERN.findall(text):
        try:
            values.add(Decimal(token).normalize())
        except InvalidOperation:
            continue
    return values


def _display_number(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def audit_model_output(generated: AnalysisOutput, grounding: AnalysisOutput) -> AuditResult:
    """Reject narrative additions that drift from deterministic evidence."""

    findings: list[str] = []
    generated_text = "\n".join(
        [generated.conclusion_text, generated.missing_data_text, generated.result_markdown]
    )
    for phrase in PROHIBITED_CAUSAL_PHRASES:
        if phrase in generated_text:
            findings.append(f"包含过度因果表述：{phrase}")
    grounding_json = grounding.model_dump_json(exclude_none=True)
    known_numbers = {abs(value) for value in _numbers(grounding_json)}
    unknown_numbers = {
        value
        for value in _numbers(generated.conclusion_text)
        if abs(value) not in known_numbers and abs(value) > Decimal("1")
    }
    if unknown_numbers:
        findings.append(
            "结论含有无法溯源的数值："
            + "、".join(_display_number(value) for value in sorted(unknown_numbers))
        )
    grounding_mentions_sample = "抽样" in grounding.missing_data_text
    generated_mentions_error = "错误" in generated.conclusion_text
    if (
        grounding_mentions_sample
        and generated_mentions_error
        and "抽样" not in generated.conclusion_text
    ):
        findings.append("引用错误订单时未声明抽样限制")
    grounded_metrics = {
        str(item.get("metric_name")): item.get("metric_value") for item in grounding.key_metrics
    }
    for item in generated.key_metrics:
        name = str(item.get("metric_name"))
        if name in grounded_metrics and item.get("metric_value") != grounded_metrics[name]:
            findings.append(f"模型改写了确定性指标：{name}")
    return AuditResult(accepted=not findings, findings=tuple(findings))


def reconcile_model_output(
    generated: AnalysisOutput,
    grounding: AnalysisOutput,
) -> AnalysisOutput:
    """Keep calculations authoritative and include model prose only after audit."""

    audit = audit_model_output(generated, grounding)
    model_summary = generated.conclusion_text if audit.accepted else grounding.conclusion_text
    audit_note = (
        "模型表述已通过数值溯源和因果边界审校。"
        if audit.accepted
        else "模型表述未通过审校，已回退为确定性结论："
        + "；".join(audit.findings)
    )
    report = grounding.result_markdown.replace(
        "## 数据范围与方法",
        f"## 管理摘要\n\n{model_summary}\n\n> {audit_note}\n\n## 数据范围与方法",
        1,
    )
    evidence = [*grounding.evidence_list]
    evidence.append(
        {
            "evidence_id": "AUDIT-001",
            "source_type": "report_audit",
            "source_name": "InsightTrace report auditor",
            "sheet_name": "报告审校",
            "evidence_text": audit_note,
            "fact_level": "audit",
            "confidence": 1.0,
            "audit_findings": list(audit.findings),
            "model_output_accepted": audit.accepted,
        }
    )
    return AnalysisOutput(
        problem_definition=grounding.problem_definition,
        key_metrics=grounding.key_metrics,
        evidence_list=evidence,
        conclusion_text=grounding.conclusion_text,
        missing_data_text=grounding.missing_data_text,
        next_actions=grounding.next_actions,
        result_markdown=report,
        overall_confidence=grounding.overall_confidence,
    )


def audit_metadata(output: AnalysisOutput) -> dict[str, Any]:
    """Compact deterministic snapshot useful in task logs and tests."""

    return {
        "metric_count": len(output.key_metrics),
        "evidence_count": len(output.evidence_list),
        "confidence": output.overall_confidence,
    }
