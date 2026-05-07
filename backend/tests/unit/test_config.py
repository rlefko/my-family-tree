"""Tests for the Settings parser, especially the CORS list flexibility."""

from __future__ import annotations

import pytest

from my_family_tree.core.config import Settings, reset_settings_cache


@pytest.mark.unit
def test_cors_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    reset_settings_cache()
    assert Settings().cors_allow_origins == ["http://localhost:5173"]


@pytest.mark.unit
def test_cors_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://a,http://b , http://c ")
    reset_settings_cache()
    assert Settings().cors_allow_origins == ["http://a", "http://b", "http://c"]


@pytest.mark.unit
def test_cors_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["http://a","http://b"]')
    reset_settings_cache()
    assert Settings().cors_allow_origins == ["http://a", "http://b"]


@pytest.mark.unit
def test_cors_single(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:5173")
    reset_settings_cache()
    assert Settings().cors_allow_origins == ["http://localhost:5173"]


@pytest.mark.unit
def test_cors_empty_string_yields_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "")
    reset_settings_cache()
    assert Settings().cors_allow_origins == []


@pytest.mark.unit
def test_openai_api_key_loads_from_flat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-abc123")
    reset_settings_cache()
    s = Settings()
    assert s.openai_api_key is not None
    assert s.openai_api_key.get_secret_value() == "sk-test-abc123"
    # Grouped view should expose the same value.
    assert s.llm.openai_api_key is not None
    assert s.llm.openai_api_key.get_secret_value() == "sk-test-abc123"


@pytest.mark.unit
def test_anthropic_api_key_loads_from_flat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    reset_settings_cache()
    s = Settings()
    assert s.llm.anthropic_api_key is not None
    assert s.llm.anthropic_api_key.get_secret_value() == "sk-ant-test"


@pytest.mark.unit
def test_database_url_overrides_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:9999/db")
    reset_settings_cache()
    s = Settings()
    assert s.db.async_url == "postgresql+asyncpg://u:p@h:9999/db"


@pytest.mark.unit
def test_database_url_built_from_components_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "alice")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_HOST", "db.example")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_DB", "tree")
    reset_settings_cache()
    s = Settings()
    assert s.db.async_url == "postgresql+asyncpg://alice:secret@db.example:6543/tree"


@pytest.mark.unit
def test_s3_bucket_from_flat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_BUCKET_DOCUMENTS", "my-prod-bucket")
    monkeypatch.setenv("S3_FORCE_PATH_STYLE", "false")
    reset_settings_cache()
    s = Settings()
    assert s.s3.bucket_documents == "my-prod-bucket"
    assert s.s3.force_path_style is False


@pytest.mark.unit
def test_llm_provider_switch_from_flat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "claude-opus-4-7")
    reset_settings_cache()
    s = Settings()
    assert s.llm.default_provider == "anthropic"
    assert s.llm.default_model == "claude-opus-4-7"
