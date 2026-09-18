from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.analysis.attachment import build_attachment_analysis
from app.models.conversation import Attachment

GOLDEN_SET_PATH = Path(__file__).with_name("golden_attachment_cases.json")


def load_cases(path: Path = GOLDEN_SET_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Golden Set must be a JSON array")
    return payload


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    attachment = Attachment(
        file_name=str(case["file_name"]),
        parsed_content_json=case["payload"],
    )
    output = build_attachment_analysis(str(case["question"]), [attachment])
    errors: list[str] = []
    if output is None:
        errors.append("未识别出可分析的两期漏斗数据")
        return {"case_id": case["case_id"], "passed": False, "errors": errors}

    metrics = {item["metric_name"]: item["metric_value"] for item in output.key_metrics}
    for name, expected in case.get("expected_metrics", {}).items():
        actual = metrics.get(name)
        if actual is None or abs(float(actual) - float(expected)) > 0.01:
            errors.append(f"指标 {name}：期望 {expected}，实际 {actual}")

    evidence_text = json.dumps(output.evidence_list, ensure_ascii=False)
    evidence_text += "\n" + output.missing_data_text
    for expected_text in case.get("expected_evidence_contains", []):
        if expected_text not in evidence_text:
            errors.append(f"证据缺少：{expected_text}")

    levels = {str(item.get("fact_level")) for item in output.evidence_list}
    missing_levels = set(case.get("expected_fact_levels", [])) - levels
    if missing_levels:
        errors.append("缺少事实层级：" + "、".join(sorted(missing_levels)))

    return {"case_id": case["case_id"], "passed": not errors, "errors": errors}


def run_golden_set(path: Path = GOLDEN_SET_PATH) -> dict[str, Any]:
    results = [evaluate_case(case) for case in load_cases(path)]
    passed = sum(1 for result in results if result["passed"])
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }


def main() -> int:
    report = run_golden_set()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
