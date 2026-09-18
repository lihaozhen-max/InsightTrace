from __future__ import annotations

from typing import Literal

from app.analysis.behavior import is_behavior_question
from app.analysis.catalog import is_catalog_question
from app.schemas.context import PreviousAnalysisContext

AnalysisScenario = Literal["catalog", "behavior"]


def resolve_analysis_scenario(
    question: str,
    previous_analysis: PreviousAnalysisContext | None,
) -> tuple[AnalysisScenario | None, Literal["current_question", "previous_analysis"] | None]:
    if is_catalog_question(question):
        return "catalog", "current_question"
    if is_behavior_question(question):
        return "behavior", "current_question"
    if previous_analysis is None:
        return None, None

    source_names = {
        str(evidence.get("source_name", ""))
        for evidence in previous_analysis.evidence_list
        if isinstance(evidence, dict)
    }
    if any(source.startswith("demo_catalog.") for source in source_names):
        return "catalog", "previous_analysis"
    if any(source.startswith("demo_behavior.") for source in source_names):
        return "behavior", "previous_analysis"

    previous_text = (
        f"{previous_analysis.problem_definition} {previous_analysis.conclusion_text}"
    )
    if is_catalog_question(previous_text):
        return "catalog", "previous_analysis"
    if is_behavior_question(previous_text):
        return "behavior", "previous_analysis"
    return None, None
