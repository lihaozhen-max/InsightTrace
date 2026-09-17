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
from app.models.enums import TaskStatus
from app.services.task_lifecycle import start_task
from app.tasks.executor import execute_task, process_next_queued_task

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run task executor integration tests",
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
        async with SessionLocal() as session:
            await session.execute(
                delete(Conversation).where(Conversation.id.in_(conversation_ids))
            )
            await session.commit()

    asyncio.run(clean_up())


def _create_task(client: TestClient, created_conversation_ids: list[UUID]) -> dict:
    conversation = client.post(
        "/api/conversations",
        json={"title": f"执行器测试 {uuid4()}"},
    ).json()
    created_conversation_ids.append(UUID(conversation["id"]))
    return client.post(
        "/api/tasks",
        json={"conversation_id": conversation["id"], "input_text": "分析收入变化"},
    ).json()


def test_executor_completes_queued_task_with_result_and_events(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as client:
        login_as(client, "admin")
        task = _create_task(client, created_conversation_ids)

        assert asyncio.run(process_next_queued_task()) is True

        completed = client.get(f"/api/tasks/{task['id']}").json()
        assert completed["task_status"] == "success"
        messages = client.get(
            f"/api/conversations/{completed['conversation_id']}/messages"
        ).json()
        assert [message["role"] for message in messages] == ["user", "assistant"]
        assert "任务执行链路已完成" in messages[-1]["content"]
        logs = client.get(f"/api/tasks/{task['id']}/logs").json()
        log_types = [log["log_type"] for log in logs]
        assert "tool_start" in log_types
        assert "tool_finish" in log_types
        assert "message_start" in log_types
        assert "message_delta" in log_types
        assert "result_ready" in log_types

        async def verify_result() -> None:
            async with SessionLocal() as session:
                result = await session.scalar(
                    select(AnalysisResult).where(
                        AnalysisResult.task_id == UUID(task["id"])
                    )
                )
                assert result is not None
                assert result.generated_by.value == "demo"
                assert result.confidence == 0.3

        asyncio.run(verify_result())


def test_executor_honours_cooperative_cancellation(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as client:
        login_as(client, "admin")
        task = _create_task(client, created_conversation_ids)

        async def start() -> None:
            async with SessionLocal() as session:
                model = await session.scalar(
                    select(AnalysisTask)
                    .where(AnalysisTask.id == UUID(task["id"]))
                    .with_for_update()
                )
                assert model is not None
                await start_task(session, model)

        asyncio.run(start())
        cancelled = client.post(f"/api/tasks/{task['id']}/cancel").json()
        assert cancelled["task_status"] == "running"

        asyncio.run(execute_task(UUID(task["id"])))

        completed = client.get(f"/api/tasks/{task['id']}").json()
        assert completed["task_status"] == TaskStatus.CANCELLED
