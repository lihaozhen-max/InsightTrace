import asyncio
import os
from collections.abc import Generator
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.main import app
from app.models.analysis import AnalysisResult, AnalysisTask
from app.models.conversation import Conversation
from app.services.task_lifecycle import advance_task, complete_task, start_task
from app.services.task_recovery import recover_interrupted_tasks

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run task lifecycle integration tests",
)


def login_as(client: TestClient, role: str) -> None:
    login = client.get("/auth/login")
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    grant = client.post("/auth/mock/authorize", data={"state": state, "role": role})
    callback = client.get(grant.headers["location"])
    assert callback.status_code == 303


@pytest.fixture
def created_conversation_ids() -> Generator[list[UUID], None, None]:
    conversation_ids: list[UUID] = []
    yield conversation_ids

    async def clean_up() -> None:
        if not conversation_ids:
            return
        async with SessionLocal() as session:
            await session.execute(
                delete(Conversation).where(Conversation.id.in_(conversation_ids))
            )
            await session.commit()

    asyncio.run(clean_up())


def test_success_transition_saves_result_and_assistant_message_atomically(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as client:
        login_as(client, "admin")
        conversation = client.post(
            "/api/conversations",
            json={"title": f"成功状态测试 {uuid4()}"},
        ).json()
        created_conversation_ids.append(UUID(conversation["id"]))
        task = client.post(
            "/api/tasks",
            json={"conversation_id": conversation["id"], "input_text": "分析收入变化"},
        ).json()

        async def run_lifecycle() -> UUID:
            async with SessionLocal() as session:
                model = await session.scalar(
                    select(AnalysisTask)
                    .where(AnalysisTask.id == UUID(task["id"]))
                    .with_for_update()
                )
                assert model is not None
                await start_task(session, model)
                await advance_task(
                    session,
                    model,
                    step="building_evidence",
                    description="正在整理证据",
                )
                result = await complete_task(
                    session,
                    model,
                    problem_definition="收入为何变化",
                    key_metrics=[{"name": "收入", "value": 1200}],
                    evidence_list=[{"source": "demo", "summary": "收入增长"}],
                    conclusion_text="收入增长",
                    missing_data_text="无",
                    next_action_text="继续观察",
                    result_markdown="# 分析结果",
                    assistant_message="收入增长，建议继续观察。",
                    confidence=0.8,
                )
                return result.id

        result_id = asyncio.run(run_lifecycle())
        completed = client.get(f"/api/tasks/{task['id']}").json()
        assert completed["task_status"] == "success"
        assert completed["finished_at"] is not None
        messages = client.get(
            f"/api/conversations/{conversation['id']}/messages"
        ).json()
        assert [message["role"] for message in messages] == ["user", "assistant"]
        assert messages[-1]["content"] == "收入增长，建议继续观察。"
        logs = client.get(f"/api/tasks/{task['id']}/logs").json()
        assert [log["log_type"] for log in logs] == [
            "task_queued",
            "task_started",
            "task_step",
            "result_ready",
            "task_succeeded",
        ]

        async def verify_result() -> None:
            async with SessionLocal() as session:
                result = await session.get(AnalysisResult, result_id)
                assert result is not None
                assert result.conclusion_text == "收入增长"

        asyncio.run(verify_result())


def test_recovery_marks_running_tasks_failed_and_retryable(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as client:
        login_as(client, "admin")
        conversation = client.post(
            "/api/conversations",
            json={"title": f"重启恢复测试 {uuid4()}"},
        ).json()
        created_conversation_ids.append(UUID(conversation["id"]))
        task = client.post(
            "/api/tasks",
            json={"conversation_id": conversation["id"], "input_text": "模拟中断"},
        ).json()

        async def start_then_recover() -> int:
            async with SessionLocal() as session:
                model = await session.scalar(
                    select(AnalysisTask)
                    .where(AnalysisTask.id == UUID(task["id"]))
                    .with_for_update()
                )
                assert model is not None
                await start_task(session, model)
            return await recover_interrupted_tasks()

        assert asyncio.run(start_then_recover()) == 1
        recovered = client.get(f"/api/tasks/{task['id']}").json()
        assert recovered["task_status"] == "failed"
        assert recovered["error_code"] == "WORKER_RESTARTED"
        assert recovered["retryable"] is True
