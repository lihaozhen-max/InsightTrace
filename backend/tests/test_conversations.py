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
    reason="Set RUN_DB_TESTS=1 to run conversation integration tests",
)


def login_as(client: TestClient, role: str) -> None:
    login = client.get("/auth/login")
    authorize_url = login.headers["location"]
    state = parse_qs(urlparse(authorize_url).query)["state"][0]
    grant = client.post(
        "/auth/mock/authorize",
        data={"state": state, "role": role},
    )
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


def test_users_can_create_and_only_list_their_own_conversations(
    created_conversation_ids: list[UUID],
) -> None:
    title = f"商品转化分析 {uuid4()}"

    with TestClient(app, follow_redirects=False) as admin_client:
        login_as(admin_client, "admin")

        invalid = admin_client.post("/api/conversations", json={"title": "   "})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

        created = admin_client.post("/api/conversations", json={"title": f"  {title}  "})
        assert created.status_code == 201
        assert created.json()["title"] == title
        created_conversation_ids.append(UUID(created.json()["id"]))

        admin_conversations = admin_client.get("/api/conversations")
        assert admin_conversations.status_code == 200
        admin_ids = {item["id"] for item in admin_conversations.json()}
        assert created.json()["id"] in admin_ids

    with TestClient(app, follow_redirects=False) as analyst_client:
        login_as(analyst_client, "analyst")
        analyst_conversations = analyst_client.get("/api/conversations")
        analyst_ids = {item["id"] for item in analyst_conversations.json()}
        assert created.json()["id"] not in analyst_ids
