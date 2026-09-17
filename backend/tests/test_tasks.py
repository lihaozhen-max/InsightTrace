import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.main import app
from app.models.analysis import AnalysisTask
from app.models.conversation import Conversation
from app.models.enums import TaskStatus
from app.services.task_lifecycle import finish_cancelled_task

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run task integration tests",
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


def test_task_creation_concurrency_cancellation_retry_and_isolation(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as admin_client:
        login_as(admin_client, "admin")
        conversation = admin_client.post(
            "/api/conversations",
            json={"title": f"任务状态机测试 {uuid4()}"},
        ).json()
        conversation_id = conversation["id"]
        created_conversation_ids.append(UUID(conversation_id))

        missing_attachment = admin_client.post(
            "/api/tasks",
            json={
                "conversation_id": conversation_id,
                "input_text": "分析商品销量",
                "attachment_ids": [str(uuid4())],
                "analysis_mode": "demo",
            },
        )
        assert missing_attachment.status_code == 404

        created = admin_client.post(
            "/api/tasks",
            json={
                "conversation_id": conversation_id,
                "input_text": "  为什么本月销量下降？  ",
                "attachment_ids": [],
                "analysis_mode": "demo",
            },
        )
        assert created.status_code == 201
        task = created.json()
        assert task["task_status"] == "queued"
        assert task["input_text"] == "为什么本月销量下降？"
        assert task["websocket_required"] is True

        duplicate = admin_client.post(
            "/api/tasks",
            json={
                "conversation_id": conversation_id,
                "input_text": "并发任务不应创建",
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "TASK_ALREADY_ACTIVE"

        messages = admin_client.get(
            f"/api/conversations/{conversation_id}/messages"
        ).json()
        assert [item["content"] for item in messages] == ["为什么本月销量下降？"]

        listed = admin_client.get(f"/api/conversations/{conversation_id}/tasks")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [task["id"]]

        logs = admin_client.get(f"/api/tasks/{task['id']}/logs")
        assert [item["log_type"] for item in logs.json()] == ["task_queued"]

    with TestClient(app, follow_redirects=False) as analyst_client:
        login_as(analyst_client, "analyst")
        assert analyst_client.get(f"/api/tasks/{task['id']}").status_code == 404
        assert analyst_client.post(f"/api/tasks/{task['id']}/cancel").status_code == 404
        assert (
            analyst_client.get(f"/api/conversations/{conversation_id}/tasks").status_code
            == 404
        )

    with TestClient(app, follow_redirects=False) as admin_client:
        login_as(admin_client, "admin")
        cancelled = admin_client.post(f"/api/tasks/{task['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["task_status"] == "cancelled"
        assert cancelled.json()["cancel_requested_at"] is not None
        assert cancelled.json()["finished_at"] is not None

        repeated_cancel = admin_client.post(f"/api/tasks/{task['id']}/cancel")
        assert repeated_cancel.status_code == 409
        assert repeated_cancel.json()["error"]["code"] == "TASK_NOT_CANCELLABLE"

        retried = admin_client.post(f"/api/tasks/{task['id']}/retry")
        assert retried.status_code == 201
        retry_task = retried.json()
        assert retry_task["task_status"] == "queued"
        assert retry_task["retry_of_task_id"] == task["id"]

        messages_after_retry = admin_client.get(
            f"/api/conversations/{conversation_id}/messages"
        ).json()
        assert len(messages_after_retry) == 1

        assert admin_client.post(f"/api/tasks/{retry_task['id']}/cancel").status_code == 200
        archived = admin_client.patch(
            f"/api/conversations/{conversation_id}",
            json={"status": "archived"},
        )
        assert archived.status_code == 200
        archived_task = admin_client.post(
            "/api/tasks",
            json={"conversation_id": conversation_id, "input_text": "不能创建"},
        )
        assert archived_task.status_code == 409
        assert archived_task.json()["error"]["code"] == "CONVERSATION_ARCHIVED"


def test_running_task_uses_cooperative_cancellation(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as client:
        login_as(client, "admin")
        conversation = client.post(
            "/api/conversations",
            json={"title": f"运行中取消测试 {uuid4()}"},
        ).json()
        created_conversation_ids.append(UUID(conversation["id"]))
        task = client.post(
            "/api/tasks",
            json={"conversation_id": conversation["id"], "input_text": "运行任务"},
        ).json()

        async def mark_running() -> None:
            async with SessionLocal() as session:
                model = await session.get(AnalysisTask, UUID(task["id"]))
                assert model is not None
                model.task_status = TaskStatus.RUNNING
                model.started_at = datetime.now(UTC)
                await session.commit()

        asyncio.run(mark_running())
        cancellation = client.post(f"/api/tasks/{task['id']}/cancel")
        assert cancellation.status_code == 200
        assert cancellation.json()["task_status"] == "running"
        assert cancellation.json()["cancel_requested_at"] is not None
        assert cancellation.json()["finished_at"] is None
        logs = client.get(f"/api/tasks/{task['id']}/logs").json()
        assert [item["log_type"] for item in logs] == [
            "task_queued",
            "cancel_requested",
        ]

        async def finish_cancellation() -> None:
            async with SessionLocal() as session:
                model = await session.scalar(
                    select(AnalysisTask)
                    .where(AnalysisTask.id == UUID(task["id"]))
                    .with_for_update()
                )
                assert model is not None
                await finish_cancelled_task(session, model)

        asyncio.run(finish_cancellation())
        assert client.get(f"/api/tasks/{task['id']}").json()["task_status"] == "cancelled"
