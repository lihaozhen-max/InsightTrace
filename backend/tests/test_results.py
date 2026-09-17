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
from app.tasks.executor import process_next_queued_task

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run result integration tests",
)


def login_as(client: TestClient, role: str) -> None:
    login = client.get("/auth/login")
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    grant = client.post("/auth/mock/authorize", data={"state": state, "role": role})
    assert client.get(grant.headers["location"]).status_code == 303


@pytest.fixture
def created_conversation_ids() -> Generator[list[UUID], None, None]:
    ids: list[UUID] = []
    yield ids

    async def clean_up() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(Conversation).where(Conversation.id.in_(ids)))
            await session.commit()

    asyncio.run(clean_up())


def test_result_read_export_download_and_user_isolation(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as admin:
        login_as(admin, "admin")
        conversation = admin.post(
            "/api/conversations", json={"title": f"结果测试 {uuid4()}"}
        ).json()
        created_conversation_ids.append(UUID(conversation["id"]))
        task = admin.post(
            "/api/tasks",
            json={"conversation_id": conversation["id"], "input_text": "分析收入"},
        ).json()
        assert admin.get(f"/api/results/{task['id']}").status_code == 404
        assert asyncio.run(process_next_queued_task()) is True

        response = admin.get(f"/api/results/{task['id']}")
        assert response.status_code == 200
        result = response.json()
        assert result["problem_definition"] == "分析收入"
        assert len(result["key_metrics"]) == 2
        assert result["report_available"] is False
        assert len(result["next_actions"]) == 2

        exported = admin.post(f"/api/results/{task['id']}/export")
        assert exported.status_code == 200
        assert exported.json()["download_path"].endswith("/download")
        downloaded = admin.get(exported.json()["download_path"])
        assert downloaded.status_code == 200
        assert downloaded.content.decode().startswith("# 分析执行结果")
        assert "report.md" in downloaded.headers["content-disposition"]

    with TestClient(app, follow_redirects=False) as analyst:
        login_as(analyst, "analyst")
        assert analyst.get(f"/api/results/{task['id']}").status_code == 404
        assert analyst.post(f"/api/results/{task['id']}/export").status_code == 404
        assert analyst.get(f"/api/results/{task['id']}/download").status_code == 404
