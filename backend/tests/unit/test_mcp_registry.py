"""Tests for MCP registry wiring."""

from __future__ import annotations

import pytest

from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.tools import (  # noqa: F401  side-effect imports
    chunks,
    conflicts,
    documents,
    notes,
    persons,
    proposals,
    stats,
)


@pytest.mark.unit
def test_registry_is_populated() -> None:
    registry = get_registry()
    names = [t.name for t in registry.available()]
    expected = {
        "person_search",
        "person_get",
        "person_traverse",
        "document_list",
        "document_get",
        "vector_search",
        "hybrid_search",
        "conflict_list",
        "conflict_get",
        "person_propose_create",
        "tree_stats",
        "note_create",
        "note_update",
        "note_delete",
    }
    assert expected.issubset(set(names))


@pytest.mark.unit
def test_read_capability_excludes_propose_tools() -> None:
    registry = get_registry()
    read_only = {t.name for t in registry.available(capability=Capability.READ)}
    assert "person_propose_create" not in read_only
    assert "person_search" in read_only


@pytest.mark.unit
def test_propose_capability_includes_propose_tools() -> None:
    registry = get_registry()
    propose = {t.name for t in registry.available(capability=Capability.PROPOSE)}
    assert "person_propose_create" in propose


@pytest.mark.unit
def test_trivial_write_capability_includes_note_tools() -> None:
    registry = get_registry()
    trivial = {t.name for t in registry.available(capability=Capability.TRIVIAL_WRITE)}
    assert {"note_create", "note_update", "note_delete"}.issubset(trivial)
