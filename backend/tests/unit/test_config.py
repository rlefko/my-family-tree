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
