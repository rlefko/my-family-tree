"""Schema and registry tests for the `proposal_cancel` MCP tool.

End-to-end cancellation (fetch row, validate pending, update status) needs
Postgres and lives behind the in-process `ToolHost`; the project has no
integration suite yet (`backend/tests/integration/` does not exist), so this
file mirrors `test_notes_tools.py`'s convention of covering the tool shape,
the registry wiring, and the input-model guards without spinning up a
container. The handler itself is exercised indirectly the moment a real
conversation triggers it; manual smoke verification is documented in the
PR description."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from my_family_tree.mcp import tools  # noqa: F401  importing the package registers every tool
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.tools.proposals import ProposalCancelInput


@pytest.mark.unit
def test_proposal_cancel_is_registered_as_trivial_write() -> None:
    registry = get_registry()
    tool = registry.tools["proposal_cancel"]
    assert tool.capability == Capability.TRIVIAL_WRITE
    assert tool.is_read_only is False


@pytest.mark.unit
def test_proposal_cancel_visible_to_chat_default_capability() -> None:
    """Chat default capability includes TRIVIAL_WRITE, so the agent should
    see `proposal_cancel` in its available tool list."""
    registry = get_registry()
    available = {t.name for t in registry.available(capability=Capability.chat_default())}
    assert "proposal_cancel" in available


@pytest.mark.unit
def test_proposal_cancel_not_in_read_only_catalog() -> None:
    """Read-only callers (e.g. the traversal subagent host) must not see
    cancel as available, since it mutates state."""
    registry = get_registry()
    read_only = {t.name for t in registry.available(capability=Capability.READ)}
    assert "proposal_cancel" not in read_only


@pytest.mark.unit
def test_proposal_cancel_input_requires_a_reason() -> None:
    with pytest.raises(PydanticValidationError):
        ProposalCancelInput.model_validate({"proposal_id": "00000000-0000-0000-0000-000000000001"})


@pytest.mark.unit
def test_proposal_cancel_input_rejects_empty_reason() -> None:
    with pytest.raises(PydanticValidationError):
        ProposalCancelInput(
            proposal_id="00000000-0000-0000-0000-000000000001",  # type: ignore[arg-type]
            reason="",
        )


@pytest.mark.unit
def test_proposal_cancel_input_rejects_oversize_reason() -> None:
    with pytest.raises(PydanticValidationError):
        ProposalCancelInput(
            proposal_id="00000000-0000-0000-0000-000000000001",  # type: ignore[arg-type]
            reason="x" * 501,
        )
