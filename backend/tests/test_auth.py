import os
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 to run the complete mock OAuth flow",
)


def test_mock_oauth_login_and_logout_flow() -> None:
    with TestClient(app, follow_redirects=False) as client:
        unauthenticated = client.get("/api/me", headers={"X-Request-ID": "auth-test"})
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["error"]["code"] == "UNAUTHENTICATED"
        assert unauthenticated.json()["error"]["request_id"] == "auth-test"
        assert unauthenticated.headers["X-Request-ID"] == "auth-test"

        login = client.get("/auth/login")
        assert login.status_code == 303
        authorize_url = login.headers["location"]
        state = parse_qs(urlparse(authorize_url).query)["state"][0]

        authorize_page = client.get(authorize_url)
        assert authorize_page.status_code == 200
        assert "选择演示身份" in authorize_page.text

        grant = client.post(
            "/auth/mock/authorize",
            data={"state": state, "role": "admin"},
        )
        assert grant.status_code == 303
        assert grant.headers["location"].startswith("/auth/callback?")

        invalid_grant = client.post("/auth/mock/authorize", data={})
        assert invalid_grant.status_code == 422
        assert invalid_grant.json()["error"]["code"] == "VALIDATION_ERROR"

        callback = client.get(grant.headers["location"])
        assert callback.status_code == 303

        current_user = client.get("/api/me")
        assert current_user.status_code == 200
        assert current_user.json()["role"] == "admin"
        assert current_user.json()["username"] == "demo.admin"

        logout = client.post("/auth/logout")
        assert logout.status_code == 200
        assert logout.json() == {"status": "success"}

        after_logout = client.get("/api/me")
        assert after_logout.status_code == 401
