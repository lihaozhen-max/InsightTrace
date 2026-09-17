import os
from urllib.parse import urlparse

import pytest


def pytest_configure(config: pytest.Config) -> None:
    if os.getenv("RUN_DB_TESTS") != "1":
        return

    database_url = os.getenv("DATABASE_URL", "")
    database_name = urlparse(database_url.replace("postgresql+asyncpg", "postgresql")).path
    if not database_name.removeprefix("/").endswith("_test"):
        raise pytest.UsageError(
            "Database integration tests require a DATABASE_URL whose database name ends with _test"
        )
