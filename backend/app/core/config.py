from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "InsightTrace"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    app_secret_key: str = Field(min_length=32, repr=False)

    database_url: str = Field(min_length=1, repr=False)
    storage_root: str = "../storage"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    frontend_url: str = "http://localhost:3000"
    session_max_age_seconds: int = 28_800
    mock_auth_code_ttl_seconds: int = 120
    websocket_token_ttl_seconds: int = Field(default=60, gt=0, le=300)
    attachment_max_file_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    attachment_max_conversation_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    attachment_parse_max_rows: int = Field(default=100_000, gt=0)
    attachment_parse_max_columns: int = Field(default=200, gt=0)
    attachment_parse_max_sheets: int = Field(default=20, gt=0)
    attachment_parse_max_text_chars: int = Field(default=1_000_000, gt=0)
    attachment_parse_max_cell_chars: int = Field(default=10_000, gt=0)
    attachment_parse_max_json_depth: int = Field(default=30, gt=0)

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
