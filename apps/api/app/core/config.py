from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    cors_origins: str = "http://localhost:3000"
    mock_agent_delay_seconds: float = 0.4
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_tpm_budget: int = Field(default=8000, ge=1000, le=1_000_000)
    groq_turn_token_budget: int = Field(default=7000, ge=1000, le=1_000_000)
    agent_provider: Literal["mock", "groq"] = "mock"
    tmdb_api_key: SecretStr | None = None
    google_books_api_key: SecretStr | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
