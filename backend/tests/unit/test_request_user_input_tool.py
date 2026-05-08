"""Schema and echo tests for `request_user_input`. The tool persists its
inputs into the output payload so the chat-stream rehydrator can rebuild the
prompt card after a page reload without keeping any transient state on the
turn."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.tools.input import (
    RequestUserInputInput,
    RequestUserInputOutput,
    request_user_input,
)


@pytest.mark.unit
def test_tool_is_registered_as_trivial_write() -> None:
    registry = get_registry()
    tool = registry.get("request_user_input")
    assert tool.capability == Capability.TRIVIAL_WRITE
    assert tool.is_read_only is False


@pytest.mark.unit
def test_input_requires_non_empty_reason() -> None:
    with pytest.raises(PydanticValidationError):
        RequestUserInputInput(reason="")


@pytest.mark.unit
def test_input_caps_reason_at_two_thousand_chars() -> None:
    with pytest.raises(PydanticValidationError):
        RequestUserInputInput(reason="x" * 2001)


@pytest.mark.unit
async def test_handler_echoes_question_into_output() -> None:
    payload = RequestUserInputInput(reason="Which birth date is correct?")
    out = await request_user_input(_ctx(), payload)
    assert isinstance(out, RequestUserInputOutput)
    assert out.acknowledged is True
    assert out.question == "Which birth date is correct?"
    assert out.options is None
    assert out.schema_hint is None


@pytest.mark.unit
async def test_handler_preserves_options_and_schema_hint() -> None:
    payload = RequestUserInputInput(
        reason="Which Anna do you mean?",
        options=["Anna Doe (b. 1932)", "Anna Doe (b. 1958)"],
        schema_hint='{"type":"string"}',
    )
    out = await request_user_input(_ctx(), payload)
    assert out.options == ["Anna Doe (b. 1932)", "Anna Doe (b. 1958)"]
    assert out.schema_hint == '{"type":"string"}'


def _ctx() -> ToolContext:
    return ToolContext(
        session_factory=_NullSessionFactory(),  # type: ignore[arg-type]
        tree_id=uuid4(),
        capabilities=Capability.TRIVIAL_WRITE,
    )


class _NullSessionFactory:
    """Stand-in for `async_sessionmaker[AsyncSession]`. The handler does not
    open a session; this object will fail loudly if a future change adds a
    DB call that slips through."""

    def __call__(self) -> Any:
        raise AssertionError("session factory should not be invoked")
