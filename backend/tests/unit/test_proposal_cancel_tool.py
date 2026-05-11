"""Schema and registry tests for the `proposal_cancel` MCP tool.

End-to-end cancellation needs Postgres and lives behind the in-process
`ToolHost`; mirrors `test_notes_tools.py` by covering the tool shape and the
input-model guards without spinning up a container."""

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
