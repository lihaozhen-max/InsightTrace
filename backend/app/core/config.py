from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "InsightTrace"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    app_secret_key: str = "development-only-change-me"

    database_url: str = (
        "postgresql+asyncpg://insighttrace:insighttrace_dev_password@localhost:5432/insighttrace"
    )
    storage_root: str = "../storage"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    analysis_mode: Literal["demo", "model"] = "demo"
    openai_base_url: str | None = None
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_root).resolve()

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
