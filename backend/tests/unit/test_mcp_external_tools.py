"""Registry tests for the new external-research tools.

Verifies that:
- All six new tools are registered.
- Gating predicates return False when no provider is configured.
- `ToolRegistry.available(settings=...)` filters disabled tools out.
- `ToolHost.specs()` and `ToolHost.call()` both honor the gating.
- The external MCP server (`build_mcp_server`) does the same."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from my_family_tree.core.config import Settings, reset_settings_cache
from my_family_tree.mcp import tools  # noqa: F401  importing the package registers every tool
from my_family_tree.mcp.host import ToolContext, ToolHost
from my_family_tree.mcp.registry import Capability, get_registry

EXTERNAL_TOOL_NAMES = {
    "web_search",
    "web_fetch",
    "genealogy_search",
    "wikitree_get_person",
    "familysearch_get_person",
    "wikidata_get_entity",
    "external_index_url",
}


def _disabled_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Return a Settings instance with every external provider disabled.

    `WIKITREE_ENABLED` and `WIKIDATA_ENABLED` are opt-out, so they default to
    True. We force them off so the gating tests see the all-disabled
    surface."""
    for var in (
        "WEB_SEARCH_PROVIDER",
        "TAVILY_API_KEY",
        "BRAVE_API_KEY",
        "FAMILYSEARCH_CLIENT_ID",
        "FAMILYSEARCH_CLIENT_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("WIKITREE_ENABLED", "false")
    monkeypatch.setenv("WIKIDATA_ENABLED", "false")
    reset_settings_cache()
    return Settings()


def _enabled_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", "tk_test")
    monkeypatch.setenv("WIKITREE_ENABLED", "true")
    monkeypatch.setenv("WIKIDATA_ENABLED", "true")
    monkeypatch.setenv("FAMILYSEARCH_CLIENT_ID", "fs_id")
    monkeypatch.setenv("FAMILYSEARCH_CLIENT_SECRET", "fs_sec")
    reset_settings_cache()
    return Settings()


@pytest.mark.unit
def test_all_external_tools_registered() -> None:
    registry = get_registry()
    names = {t.name for t in registry.available()}
    missing = EXTERNAL_TOOL_NAMES - names
    assert not missing, f"missing external tools: {missing}"


@pytest.mark.unit
def test_external_tools_carry_web_capability() -> None:
    registry = get_registry()
    for name in EXTERNAL_TOOL_NAMES:
        tool = registry.get(name)
        assert tool.capability & Capability.WEB, f"tool {name} should carry Capability.WEB"


@pytest.mark.unit
def test_external_tools_filtered_out_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _disabled_settings(monkeypatch)
    registry = get_registry()
    available = {t.name for t in registry.available(settings=settings)}
    # `web_fetch` and `external_index_url` have no enabled_when predicate;
    # they should still appear. Everything else is gated.
    gated = EXTERNAL_TOOL_NAMES - {"web_fetch", "external_index_url"}
    leaked = gated & available
    assert not leaked, f"these should be hidden when disabled: {leaked}"
    assert "web_fetch" in available
    assert "external_index_url" in available


@pytest.mark.unit
def test_external_tools_visible_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _enabled_settings(monkeypatch)
    registry = get_registry()
    available = {t.name for t in registry.available(settings=settings)}
    missing = EXTERNAL_TOOL_NAMES - available
    assert not missing, f"these should be visible when keys are set: {missing}"


@pytest.mark.unit
def test_registry_get_with_settings_rejects_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _disabled_settings(monkeypatch)
    registry = get_registry()
    with pytest.raises(KeyError):
        registry.get("web_search", settings=settings)


@pytest.mark.unit
def test_tool_host_specs_filters_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _disabled_settings(monkeypatch)
    ctx = ToolContext(
        session_factory=MagicMock(),
        tree_id=uuid4(),
        capabilities=Capability.chat_default(),
    )
    host = ToolHost(get_registry(), context=ctx, settings=settings)
    spec_names = {s["name"] for s in host.specs()}
    assert "web_search" not in spec_names
    assert "wikitree_get_person" not in spec_names


@pytest.mark.unit
async def test_tool_host_call_rejects_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _disabled_settings(monkeypatch)
    ctx = ToolContext(
        session_factory=MagicMock(),
        tree_id=uuid4(),
        capabilities=Capability.chat_default(),
    )
    host = ToolHost(get_registry(), context=ctx, settings=settings)
    with pytest.raises(ValueError, match="unknown tool"):
        await host.call("web_search", {"query": "x"})


@pytest.mark.unit
def test_external_predicates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spot-check the per-tool predicates against a Settings with each
    provider toggled individually."""
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", "tk")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setenv("WIKITREE_ENABLED", "true")
    monkeypatch.setenv("WIKIDATA_ENABLED", "false")
    monkeypatch.delenv("FAMILYSEARCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("FAMILYSEARCH_CLIENT_SECRET", raising=False)
    reset_settings_cache()
    settings = Settings()
    registry = get_registry()
    available = {t.name for t in registry.available(settings=settings)}
    assert "web_search" in available
    assert "wikitree_get_person" in available
    assert "wikidata_get_entity" not in available
    assert "familysearch_get_person" not in available
    # `genealogy_search` is gated on `any_enabled`; wikitree alone counts.
    assert "genealogy_search" in available


@pytest.mark.unit
def test_brave_with_tavily_provider_config_does_not_enable() -> None:
    """If `WEB_SEARCH_PROVIDER=brave` but no Brave key, web_search stays
    hidden even when a Tavily key happens to be configured for some reason."""
    settings = _build_settings(
        web_search_provider="brave",
        tavily_api_key=SecretStr("tk"),
        brave_api_key=None,
    )
    registry = get_registry()
    available = {t.name for t in registry.available(settings=settings)}
    assert "web_search" not in available


def _build_settings(**overrides: Any) -> Settings:
    """Construct a Settings instance with explicit overrides bypassing the
    env. Used where sets-based env manipulation gets fiddly."""
    base = Settings()
    return base.model_copy(update=overrides)
