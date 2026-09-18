import json
from uuid import uuid4

import pytest

from app.analysis.providers import openai_compatible
from app.schemas.context import AnalysisContext


def _context() -> AnalysisContext:
    return AnalysisContext(
        conversation_id=uuid4(),
        task_id=uuid4(),
        current_question="为什么收入下降？",
        earlier_summary=None,
        recent_messages=[],
        previous_analysis=None,
        attachments=[],
    )


@pytest.mark.asyncio
async def test_provider_calls_chat_completions_and_validates_output(monkeypatch) -> None:
    output = {
        "problem_definition": "分析收入下降原因",
        "key_metrics": [],
        "evidence_list": [],
        "conclusion_text": "当前数据不足，无法确认原因。",
        "missing_data_text": "缺少收入明细。",
        "next_actions": ["补充收入明细"],
        "result_markdown": "# 分析结果\n\n当前数据不足。",
        "overall_confidence": 0.2,
    }
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": json.dumps(output)}}]}
            ).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(openai_compatible, "urlopen", fake_urlopen)

    result = await openai_compatible.analyze_with_openai_compatible(
        _context(),
        base_url="https://example.test/v1",
        api_key="secret",
        model="test-model",
        timeout_seconds=12,
        grounding_output=openai_compatible.AnalysisOutput(**output),
    )

    assert result.conclusion_text == output["conclusion_text"]
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["timeout"] == 12
    assert captured["body"]["model"] == "test-model"
    assert "为什么收入下降" in captured["body"]["messages"][1]["content"]
    assert "系统工具已经计算出的可信结果" in captured["body"]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_provider_rejects_invalid_model_output(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"choices":[{"message":{"content":"{}"}}]}'

    monkeypatch.setattr(openai_compatible, "urlopen", lambda *args, **kwargs: Response())

    with pytest.raises(openai_compatible.ModelProviderError, match="AnalysisOutput"):
        await openai_compatible.analyze_with_openai_compatible(
            _context(),
            base_url="https://example.test/v1",
            api_key="secret",
            model="test-model",
        )
