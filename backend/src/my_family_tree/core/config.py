"""Application settings loaded from env via pydantic-settings.

Settings are flat at the env layer so a `.env` file that uses the worldwide
conventional names (`OPENAI_API_KEY`, `DATABASE_URL`, `S3_ENDPOINT_URL`,
etc.) Just Works without ceremony. The grouped accessors `settings.db`,
`settings.s3`, `settings.llm`, etc. are computed views over those flat
fields, so callers continue using `settings.llm.openai_api_key` while the
env file stays human-friendly.

`Settings()` is constructed once via `get_settings()` (lru_cache) and shared
across the app's lifespan."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# --- view dataclasses (read-only groupings over the flat Settings) ---------


@dataclass(slots=True, frozen=True)
class DBView:
    user: str
    password: SecretStr
    name: str
    host: str
    port: int
    url: str | None
    url_sync: str | None
    pool_size: int
    max_overflow: int
    echo: bool

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


@dataclass(slots=True, frozen=True)
class RedisView:
    url: str


@dataclass(slots=True, frozen=True)
class S3View:
    endpoint_url: str | None
    region: str
    access_key: SecretStr
    secret_key: SecretStr
    bucket_documents: str
    force_path_style: bool


@dataclass(slots=True, frozen=True)
class LLMView:
    openai_api_key: SecretStr | None
    anthropic_api_key: SecretStr | None
    default_provider: Literal["openai", "anthropic"]
    default_model: str
    default_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh"]
    embedding_model: str
    embedding_dims: int
    vision_model: str
    request_timeout_s: float


@dataclass(slots=True, frozen=True)
class OCRView:
    tesseract_bin: str
    vision_fallback_provider: Literal["openai", "anthropic"]
    vision_fallback_daily_usd_cap: float
    vision_fallback_enabled: bool
    tesseract_min_confidence: int


@dataclass(slots=True, frozen=True)
class MCPView:
    http_host: str
    http_port: int


@dataclass(slots=True, frozen=True)
class WebSearchView:
    provider: Literal["", "tavily", "brave", "openai_native", "anthropic_native"]
    tavily_api_key: SecretStr | None
    brave_api_key: SecretStr | None


@dataclass(slots=True, frozen=True)
class ObservabilityView:
    otel_exporter_otlp_endpoint: str | None
    sentry_dsn: SecretStr | None


# --- root Settings (flat env-driven fields) --------------------------------


class Settings(BaseSettings):
    """Flat settings driven by environment variables. Field names are the env
    var names (case-insensitive). See the grouped accessors below for the
    ergonomic API used in code."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---------------------------------------------------------------
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "My Family Tree"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    secret_key: SecretStr = SecretStr("change-me-in-production")
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

    # --- Postgres ----------------------------------------------------------
    postgres_user: str = "my_family_tree"
    postgres_password: SecretStr = SecretStr("my_family_tree")
    postgres_db: str = "my_family_tree"
    postgres_host: str = "db"
    postgres_port: int = 5432
    database_url: str | None = None
    database_url_sync: str | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # --- Redis -------------------------------------------------------------
    redis_url: str = "redis://redis:6379/0"

    # --- S3 / MinIO --------------------------------------------------------
    s3_endpoint_url: str | None = "http://minio:9000"
    s3_region: str = "us-east-1"
    s3_access_key: SecretStr = SecretStr("my-family-tree-local")
    s3_secret_key: SecretStr = SecretStr("my-family-tree-local-secret")
    s3_bucket_documents: str = "my-family-tree"
    s3_force_path_style: bool = True

    # --- LLM ---------------------------------------------------------------
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    llm_default_provider: Literal["openai", "anthropic"] = "openai"
    llm_default_model: str = "gpt-5.5"
    llm_default_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh"] = "high"
    llm_embedding_model: str = "text-embedding-3-large"
    llm_embedding_dims: int = 3072
    llm_vision_model: str = "gpt-4o-mini"
    llm_request_timeout_s: float = 120.0

    # --- OCR ---------------------------------------------------------------
    tesseract_bin: str = "/usr/bin/tesseract"
    vision_fallback_provider: Literal["openai", "anthropic"] = "openai"
    vision_fallback_daily_usd_cap: float = 5.00
    vision_fallback_enabled: bool = True
    tesseract_min_confidence: int = 60

    # --- Uploads -----------------------------------------------------------
    max_upload_bytes: int = 50 * 1024 * 1024

    # --- MCP ---------------------------------------------------------------
    mcp_http_host: str = "0.0.0.0"
    mcp_http_port: int = 8765

    # --- Web search --------------------------------------------------------
    web_search_provider: Literal["", "tavily", "brave", "openai_native", "anthropic_native"] = ""
    tavily_api_key: SecretStr | None = None
    brave_api_key: SecretStr | None = None

    # --- Observability -----------------------------------------------------
    otel_exporter_otlp_endpoint: str | None = None
    sentry_dsn: SecretStr | None = None

    # --- Convenience -------------------------------------------------------
    @property
    def is_dev(self) -> bool:
        return self.app_env in {"development", "test"}

    # --- Grouped accessors -------------------------------------------------
    # These exist purely so callers can keep writing `settings.llm.openai_api_key`
    # without each consumer needing to know the flat field names. They are
    # computed each access (cheap, frozen dataclasses).

    @property
    def db(self) -> DBView:
        return DBView(
            user=self.postgres_user,
            password=self.postgres_password,
            name=self.postgres_db,
            host=self.postgres_host,
            port=self.postgres_port,
            url=self.database_url,
            url_sync=self.database_url_sync,
            pool_size=self.db_pool_size,
            max_overflow=self.db_max_overflow,
            echo=self.db_echo,
        )

    @property
    def redis(self) -> RedisView:
        return RedisView(url=self.redis_url)

    @property
    def s3(self) -> S3View:
        return S3View(
            endpoint_url=self.s3_endpoint_url,
            region=self.s3_region,
            access_key=self.s3_access_key,
            secret_key=self.s3_secret_key,
            bucket_documents=self.s3_bucket_documents,
            force_path_style=self.s3_force_path_style,
        )

    @property
    def llm(self) -> LLMView:
        return LLMView(
            openai_api_key=self.openai_api_key,
            anthropic_api_key=self.anthropic_api_key,
            default_provider=self.llm_default_provider,
            default_model=self.llm_default_model,
            default_reasoning_effort=self.llm_default_reasoning_effort,
            embedding_model=self.llm_embedding_model,
            embedding_dims=self.llm_embedding_dims,
            vision_model=self.llm_vision_model,
            request_timeout_s=self.llm_request_timeout_s,
        )

    @property
    def ocr(self) -> OCRView:
        return OCRView(
            tesseract_bin=self.tesseract_bin,
            vision_fallback_provider=self.vision_fallback_provider,
            vision_fallback_daily_usd_cap=self.vision_fallback_daily_usd_cap,
            vision_fallback_enabled=self.vision_fallback_enabled,
            tesseract_min_confidence=self.tesseract_min_confidence,
        )

    @property
    def mcp(self) -> MCPView:
        return MCPView(http_host=self.mcp_http_host, http_port=self.mcp_http_port)

    @property
    def web_search(self) -> WebSearchView:
        return WebSearchView(
            provider=self.web_search_provider,
            tavily_api_key=self.tavily_api_key,
            brave_api_key=self.brave_api_key,
        )

    @property
    def obs(self) -> ObservabilityView:
        return ObservabilityView(
            otel_exporter_otlp_endpoint=self.otel_exporter_otlp_endpoint,
            sentry_dsn=self.sentry_dsn,
        )


# Backwards-compatible aliases so other modules can still import these names.
DBSettings = DBView
RedisSettings = RedisView
S3Settings = S3View
LLMSettings = LLMView
OCRSettings = OCRView
MCPSettings = MCPView
WebSearchSettings = WebSearchView
ObservabilitySettings = ObservabilityView


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton. Cached so env is read once."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached Settings. Used by tests that mutate env vars."""
    get_settings.cache_clear()
