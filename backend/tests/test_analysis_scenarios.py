from app.analysis.scenarios import resolve_analysis_scenario
from app.schemas.context import PreviousAnalysisContext


def previous_analysis(source_name: str) -> PreviousAnalysisContext:
    return PreviousAnalysisContext(
        problem_definition="上一轮问题",
        conclusion_text="上一轮结论",
        key_metrics=[],
        evidence_list=[{"source_name": source_name}],
    )


def test_explicit_question_takes_priority_over_previous_scenario() -> None:
    scenario, source = resolve_analysis_scenario(
        "为什么商品目录转化下降？",
        previous_analysis("demo_behavior.funnel_metrics"),
    )

    assert scenario == "catalog"
    assert source == "current_question"


def test_follow_up_inherits_catalog_scenario_from_evidence_source() -> None:
    scenario, source = resolve_analysis_scenario(
        "再具体一点，谁贡献最大？",
        previous_analysis("demo_catalog.funnel_metrics"),
    )

    assert scenario == "catalog"
    assert source == "previous_analysis"


def test_follow_up_inherits_behavior_scenario_from_evidence_source() -> None:
    scenario, source = resolve_analysis_scenario(
        "那最值得先检查哪一群人？",
        previous_analysis("demo_behavior.funnel_metrics"),
    )

    assert scenario == "behavior"
    assert source == "previous_analysis"


def test_ambiguous_question_without_history_has_no_scenario() -> None:
    assert resolve_analysis_scenario("再具体一点？", None) == (None, None)
