"""Application settings, loaded from .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM (OpenRouter) ──────────────────────────────────────────────────
    openrouter_api_key: str = ""
    interview_model: str = "anthropic/claude-sonnet-4.6"
    interview_max_tokens: int = 800

    # ── LangSmith tracing ─────────────────────────────────────────────────
    langsmith_project: str = "interview-prep"

    # ── API server ────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://localhost:8501"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
