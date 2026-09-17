import asyncio
import hashlib
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
    reason="Set RUN_DB_TESTS=1 to run attachment integration tests",
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


def test_attachment_lifecycle_and_user_isolation(
    created_conversation_ids: list[UUID],
) -> None:
    content = b"product_id,revenue\nA-1,1200\n"

    with TestClient(app, follow_redirects=False) as admin_client:
        login_as(admin_client, "admin")
        created = admin_client.post(
            "/api/conversations",
            json={"title": f"附件集成测试 {uuid4()}"},
        )
        assert created.status_code == 201
        conversation_id = created.json()["id"]
        created_conversation_ids.append(UUID(conversation_id))
        attachment_url = f"/api/conversations/{conversation_id}/attachments"

        unsupported = admin_client.post(
            attachment_url,
            files={"file": ("danger.exe", b"not executable", "application/octet-stream")},
        )
        assert unsupported.status_code == 415
        assert unsupported.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"

        uploaded = admin_client.post(
            attachment_url,
            files={"file": ("sales.csv", content, "text/csv")},
        )
        assert uploaded.status_code == 201
        attachment = uploaded.json()
        assert attachment["file_name"] == "sales.csv"
        assert attachment["file_size"] == len(content)
        assert attachment["sha256"] == hashlib.sha256(content).hexdigest()
        assert attachment["parse_status"] == "success"
        assert attachment["parse_error"] is None

        reparsed = admin_client.post(
            f"{attachment_url}/{attachment['id']}/parse"
        )
        assert reparsed.status_code == 200
        assert reparsed.json()["parse_status"] == "success"

        invalid_json = admin_client.post(
            attachment_url,
            files={"file": ("broken.json", b'{"missing":', "application/json")},
        )
        assert invalid_json.status_code == 201
        assert invalid_json.json()["parse_status"] == "failed"
        assert "JSON 格式错误" in invalid_json.json()["parse_error"]

        listed = admin_client.get(attachment_url)
        assert listed.status_code == 200
        assert {item["id"] for item in listed.json()} == {
            attachment["id"],
            invalid_json.json()["id"],
        }

        downloaded = admin_client.get(
            f"{attachment_url}/{attachment['id']}/download"
        )
        assert downloaded.status_code == 200
        assert downloaded.content == content
        assert "sales.csv" in downloaded.headers["content-disposition"]

        archived = admin_client.patch(
            f"/api/conversations/{conversation_id}",
            json={"status": "archived"},
        )
        assert archived.status_code == 200
        archived_upload = admin_client.post(
            attachment_url,
            files={"file": ("later.txt", b"later", "text/plain")},
        )
        assert archived_upload.status_code == 409
        assert archived_upload.json()["error"]["code"] == "CONVERSATION_ARCHIVED"

    with TestClient(app, follow_redirects=False) as analyst_client:
        login_as(analyst_client, "analyst")
        inaccessible = analyst_client.get(attachment_url)
        assert inaccessible.status_code == 404
        inaccessible_download = analyst_client.get(
            f"{attachment_url}/{attachment['id']}/download"
        )
        assert inaccessible_download.status_code == 404

    with TestClient(app, follow_redirects=False) as admin_client:
        login_as(admin_client, "admin")
        deleted = admin_client.delete(f"{attachment_url}/{attachment['id']}")
        assert deleted.status_code == 204
        missing = admin_client.get(f"{attachment_url}/{attachment['id']}/download")
        assert missing.status_code == 404
