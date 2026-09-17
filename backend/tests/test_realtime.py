import asyncio
import hashlib
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.main import app
from app.models.conversation import Conversation
from app.models.identity import WebSocketToken
from app.tasks.executor import process_next_queued_task

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run realtime integration tests",
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


def websocket_url(conversation_id: str, token: str) -> str:
    query = urlencode(
        {"conversation_id": conversation_id, "websocket_token": token}
    )
    return f"/api/chat/ws/chat?{query}"


def test_one_time_websocket_token_and_initial_task_event(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as admin_client:
        login_as(admin_client, "admin")
        conversation = admin_client.post(
            "/api/conversations",
            json={"title": f"实时连接测试 {uuid4()}"},
        ).json()
        conversation_id = conversation["id"]
        created_conversation_ids.append(UUID(conversation_id))
        task = admin_client.post(
            "/api/tasks",
            json={"conversation_id": conversation_id, "input_text": "实时任务"},
        ).json()

        issued = admin_client.post(
            "/api/chat/ws-token",
            json={"conversation_id": conversation_id},
        )
        assert issued.status_code == 200
        token = issued.json()["token"]
        assert token not in issued.json()["websocket_path"]

        with admin_client.websocket_connect(websocket_url(conversation_id, token)) as socket:
            connected = socket.receive_json()
            assert connected["event_type"] == "connected"
            assert connected["seq_no"] == 0
            status_event = socket.receive_json()
            assert status_event["event_type"] == "task_status"
            assert status_event["task_id"] == task["id"]
            assert status_event["payload"]["task_status"] == "queued"

        with admin_client.websocket_connect(websocket_url(conversation_id, token)) as reused:
            error = reused.receive_json()
            assert error["event_type"] == "error"
            assert error["payload"]["error_code"] == "WEBSOCKET_TOKEN_INVALID"

    with TestClient(app, follow_redirects=False) as analyst_client:
        login_as(analyst_client, "analyst")
        inaccessible = analyst_client.post(
            "/api/chat/ws-token",
            json={"conversation_id": conversation_id},
        )
        assert inaccessible.status_code == 404


def test_expired_websocket_token_is_rejected(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as client:
        login_as(client, "admin")
        conversation = client.post(
            "/api/conversations",
            json={"title": f"过期令牌测试 {uuid4()}"},
        ).json()
        conversation_id = conversation["id"]
        created_conversation_ids.append(UUID(conversation_id))
        issued = client.post(
            "/api/chat/ws-token",
            json={"conversation_id": conversation_id},
        ).json()

        async def expire_token() -> None:
            async with SessionLocal() as session:
                token = await session.scalar(
                    select(WebSocketToken).where(
                        WebSocketToken.token_hash
                        == hashlib.sha256(issued["token"].encode()).hexdigest()
                    )
                )
                assert token is not None
                token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await session.commit()

        asyncio.run(expire_token())
        with client.websocket_connect(
            websocket_url(conversation_id, issued["token"])
        ) as socket:
            error = socket.receive_json()
            assert error["payload"]["error_code"] == "WEBSOCKET_TOKEN_INVALID"


def test_completed_task_replays_persisted_execution_events(
    created_conversation_ids: list[UUID],
) -> None:
    with TestClient(app, follow_redirects=False) as client:
        login_as(client, "admin")
        conversation = client.post(
            "/api/conversations",
            json={"title": f"完整事件测试 {uuid4()}"},
        ).json()
        conversation_id = conversation["id"]
        created_conversation_ids.append(UUID(conversation_id))
        client.post(
            "/api/tasks",
            json={"conversation_id": conversation_id, "input_text": "分析经营变化"},
        )
        assert asyncio.run(process_next_queued_task()) is True
        issued = client.post(
            "/api/chat/ws-token",
            json={"conversation_id": conversation_id},
        ).json()

        with client.websocket_connect(
            websocket_url(conversation_id, issued["token"])
        ) as socket:
            events = []
            while not events or events[-1]["event_type"] != "done":
                events.append(socket.receive_json())

        event_types = [event["event_type"] for event in events]
        assert event_types[0] == "connected"
        assert "task_status" in event_types
        assert "message_start" in event_types
        assert "message_delta" in event_types
        assert "tool_start" in event_types
        assert "tool_finish" in event_types
        assert "result_ready" in event_types
        assert event_types[-1] == "done"
        assert [event["seq_no"] for event in events] == list(range(len(events)))
