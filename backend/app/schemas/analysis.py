from typing import Any

from pydantic import BaseModel, Field


class AnalysisOutput(BaseModel):
    """Validated result contract shared by demo and future model providers."""

    problem_definition: str = Field(min_length=1)
    key_metrics: list[dict[str, Any]]
    evidence_list: list[dict[str, Any]]
    conclusion_text: str = Field(min_length=1)
    missing_data_text: str
    next_actions: list[str]
    result_markdown: str = Field(min_length=1)
    overall_confidence: float | None = Field(default=None, ge=0, le=1)

    @property
    def next_action_text(self) -> str:
        return "\n".join(f"- {item}" for item in self.next_actions)
