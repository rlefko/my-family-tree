"""Registry tests for the propose-write tool surface."""

from __future__ import annotations

import pytest

from my_family_tree.mcp import tools  # noqa: F401  importing the package registers every tool
from my_family_tree.mcp.registry import Capability, get_registry

PROPOSE_TOOLS = {
    "person_propose_create",
    "person_propose_update",
    "person_propose_merge",
    "relationship_propose_create",
    "relationship_propose_delete",
    "event_propose_create",
    "event_propose_update",
    "place_propose_create",
    "source_propose_create",
    "claim_propose_accept",
    "claim_propose_reject",
}

READ_TOOLS = {
    "person_search",
    "person_get",
    "person_traverse",
    "person_relations",
    "person_count_relations",
    "traverse_and_summarize",
    "place_search",
    "document_list",
    "document_get",
    "vector_search",
    "hybrid_search",
    "conflict_list",
    "conflict_get",
    "tree_stats",
    "web_search",
    "web_fetch",
    "genealogy_search",
    "wikitree_get_person",
    "familysearch_get_person",
    "wikidata_get_entity",
}


@pytest.mark.unit
def test_all_propose_tools_registered() -> None:
    registry = get_registry()
    names = {t.name for t in registry.available()}
    missing = PROPOSE_TOOLS - names
    assert not missing, f"missing propose tools: {missing}"


@pytest.mark.unit
def test_propose_tools_have_propose_capability() -> None:
    registry = get_registry()
    for name in PROPOSE_TOOLS:
        tool = registry.get(name)
        assert tool.capability & Capability.PROPOSE, (
            f"tool {name} should be tagged with Capability.PROPOSE"
        )
        assert tool.is_read_only is False


@pytest.mark.unit
def test_propose_tools_excluded_from_read_capability() -> None:
    registry = get_registry()
    read_only = {t.name for t in registry.available(capability=Capability.READ)}
    overlap = PROPOSE_TOOLS & read_only
    assert not overlap, f"propose tools should not appear in READ capability: {overlap}"


@pytest.mark.unit
def test_request_user_input_is_trivial_write() -> None:
    registry = get_registry()
    tool = registry.get("request_user_input")
    assert tool.capability & Capability.TRIVIAL_WRITE


@pytest.mark.unit
def test_chat_default_capability_includes_propose_and_read() -> None:
    cap = Capability.chat_default()
    assert cap & Capability.READ
    assert cap & Capability.PROPOSE
    assert cap & Capability.TRIVIAL_WRITE
    assert cap & Capability.WEB


@pytest.mark.unit
def test_read_tools_present() -> None:
    registry = get_registry()
    names = {t.name for t in registry.available()}
    missing = READ_TOOLS - names
    assert not missing, f"missing read tools: {missing}"
