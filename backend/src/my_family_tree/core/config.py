"""Application settings loaded from env via pydantic-settings.

Conventions:
- Nested settings groups use the `__` env delimiter (e.g. `LLM__DEFAULT_MODEL`).
- Flat aliases are kept for the most common values (see `model_config.alias_generator`).
- `Settings()` is constructed once via `get_settings()` (lru_cache) and shared
  across the app's lifespan.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class DBSettings(BaseModel):
    """Postgres connection settings."""

    user: str = "my_family_tree"
    password: SecretStr = SecretStr("my_family_tree")
    name: str = "my_family_tree"
    host: str = "db"
    port: int = 5432
    url: str | None = None
    url_sync: str | None = None
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False

    @property
    def async_url(self) -> str:
        if self.url:
            return self.url
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def sync_url(self) -> str:
        if self.url_sync:
            return self.url_sync
        return (
            f"postgresql+psycopg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class RedisSettings(BaseModel):
    url: str = "redis://redis:6379/0"


class S3Settings(BaseModel):
    """Object storage. Defaults target MinIO locally; in prod set
    `endpoint_url=None` and rely on real S3 credentials from the environment."""

    endpoint_url: str | None = "http://minio:9000"
    region: str = "us-east-1"
    access_key: SecretStr = SecretStr("my-family-tree-local")
    secret_key: SecretStr = SecretStr("my-family-tree-local-secret")
    bucket_documents: str = "my-family-tree"
    force_path_style: bool = True


class LLMSettings(BaseModel):
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    default_provider: Literal["openai", "anthropic"] = "openai"
    default_model: str = "gpt-5.5"
    default_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh"] = "high"
    embedding_model: str = "text-embedding-3-large"
    embedding_dims: int = 3072
    request_timeout_s: float = 120.0


class OCRSettings(BaseModel):
    tesseract_bin: str = "/usr/bin/tesseract"
    vision_fallback_provider: Literal["openai", "anthropic"] = "openai"
    vision_fallback_daily_usd_cap: float = 5.00
    tesseract_min_confidence: int = 60


class MCPSettings(BaseModel):
    http_host: str = "0.0.0.0"
    http_port: int = 8765


class WebSearchSettings(BaseModel):
    provider: Literal["", "tavily", "brave", "openai_native", "anthropic_native"] = ""
    tavily_api_key: SecretStr | None = None
    brave_api_key: SecretStr | None = None


class ObservabilitySettings(BaseModel):
    otel_exporter_otlp_endpoint: str | None = None
    sentry_dsn: SecretStr | None = None


class Settings(BaseSettings):
    """Root settings. All env vars use `__` for nesting and `_` for word breaks."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "My Family Tree"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    secret_key: SecretStr = SecretStr("change-me-in-production")
    # `NoDecode` opts out of pydantic-settings' default JSON decoding for env
    # values. The validator below accepts plain comma-separated strings so a
    # human-friendly `.env` (`CORS_ALLOW_ORIGINS=http://a,http://b`) works the
    # same as a JSON array.
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_cors_list(cls, value: object) -> object:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    db: DBSettings = Field(default_factory=DBSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    s3: S3Settings = Field(default_factory=S3Settings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    ocr: OCRSettings = Field(default_factory=OCRSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    web_search: WebSearchSettings = Field(default_factory=WebSearchSettings)
    obs: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    @property
    def is_dev(self) -> bool:
        return self.app_env in {"development", "test"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton. Cached so env is read once."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached Settings. Used by tests that mutate env vars."""
    get_settings.cache_clear()
