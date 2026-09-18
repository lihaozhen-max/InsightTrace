import asyncio
import os
from collections.abc import Generator
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models.conversation import Conversation

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run admin integration tests",
)


def login_as(client: TestClient, role: str) -> None:
    login = client.get("/auth/login")
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    grant = client.post("/auth/mock/authorize", data={"state": state, "role": role})
    assert client.get(grant.headers["location"]).status_code == 303


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


def test_admin_can_inspect_health_reload_safe_config_and_view_tasks(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as client:
        login_as(client, "admin")
        health = client.get("/api/admin/health")
        assert health.status_code == 200
        assert health.json()["database"] == "ok"
        assert "openai_api_key" not in health.text

        configs = client.get("/api/admin/configs")
        assert configs.status_code == 200
        config_keys = {item["key"] for item in configs.json()["items"]}
        assert "sql_statement_timeout_ms" in config_keys
        assert not {"app_secret_key", "database_url", "openai_api_key"} & config_keys

        reloaded = client.post("/api/admin/reload")
        assert reloaded.status_code == 200
        assert reloaded.json()["reloaded_at"] is not None

        conversation = client.post(
            "/api/conversations",
            json={"title": f"管理日志测试 {uuid4()}"},
        ).json()
        created_conversation_ids.append(UUID(conversation["id"]))
        task = client.post(
            "/api/tasks",
            json={"conversation_id": conversation["id"], "input_text": "检查任务日志"},
        ).json()

        tasks = client.get("/api/admin/tasks")
        assert tasks.status_code == 200
        selected = next(item for item in tasks.json() if item["id"] == task["id"])
        assert selected["last_log_type"] == "task_queued"
        assert selected["last_log_content"] == "分析任务已进入队列"


def test_analyst_cannot_access_admin_endpoints() -> None:
    with TestClient(app, follow_redirects=False) as client:
        login_as(client, "analyst")
        assert client.get("/api/admin/configs").status_code == 403
        assert client.post("/api/admin/reload").status_code == 403
        assert client.get("/api/admin/health").status_code == 403
        assert client.get("/api/admin/tasks").status_code == 403
