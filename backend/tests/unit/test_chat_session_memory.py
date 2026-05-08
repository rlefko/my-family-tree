"""Pure-function tests for the chat router's session-memory helpers.

`_assistant_messages_from_content` rehydrates a persisted assistant
`content_json` row into the (assistant, tool?) `LLMMessage` pair the
providers expect; `_format_session_state` renders proposal rows into the
`[Session state]` block prepended to each turn. Both are pure and tested
without a database or a request."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from my_family_tree.api.routers.chat import (
    _SESSION_STATE_HEADER,
    _assistant_messages_from_content,
    _format_session_state,
    _ProposalRow,
)
from my_family_tree.llm.base import (
    Message as LLMMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from my_family_tree.models.enums import ProposalAction, ProposalStatus, SubjectType

# --- _assistant_messages_from_content --------------------------------------


@pytest.mark.unit
def test_splitter_returns_empty_for_empty_content() -> None:
    assert _assistant_messages_from_content([]) == []


@pytest.mark.unit
def test_splitter_text_only_emits_single_assistant_message() -> None:
    out = _assistant_messages_from_content([{"type": "text", "text": "hello"}])
    assert len(out) == 1
    msg = out[0]
    assert msg.role == "assistant"
    assert len(msg.content) == 1
    block = msg.content[0]
    assert isinstance(block, TextBlock)
    assert block.text == "hello"


@pytest.mark.unit
def test_splitter_concatenates_multiple_text_blocks() -> None:
    out = _assistant_messages_from_content(
        [
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"},
        ]
    )
    assert len(out) == 1
    block = out[0].content[0]
    assert isinstance(block, TextBlock)
    assert block.text == "hello world"


@pytest.mark.unit
def test_splitter_single_tool_pairs_use_with_result() -> None:
    out = _assistant_messages_from_content(
        [
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "person_search",
                "input": {"query": "Anna"},
                "output": {"results": []},
                "is_error": False,
            }
        ]
    )
    assert len(out) == 2
    asst, tool = out
    assert asst.role == "assistant"
    assert len(asst.content) == 1
    use = asst.content[0]
    assert isinstance(use, ToolUseBlock)
    assert use.id == "call_1"
    assert use.name == "person_search"
    assert use.input == {"query": "Anna"}
    assert tool.role == "tool"
    assert len(tool.content) == 1
    result = tool.content[0]
    assert isinstance(result, ToolResultBlock)
    assert result.tool_use_id == "call_1"
    assert result.output == {"results": []}
    assert result.is_error is False


@pytest.mark.unit
def test_splitter_text_then_tool_keeps_text_first_in_assistant() -> None:
    out = _assistant_messages_from_content(
        [
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "person_search",
                "input": {"query": "Anna"},
                "output": {"results": []},
            },
            {"type": "text", "text": "done"},
        ]
    )
    assert len(out) == 2
    asst = out[0]
    assert isinstance(asst.content[0], TextBlock)
    assert asst.content[0].text == "done"
    assert isinstance(asst.content[1], ToolUseBlock)
    assert asst.content[1].id == "call_1"


@pytest.mark.unit
def test_splitter_multiple_tools_preserve_stored_order() -> None:
    out = _assistant_messages_from_content(
        [
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "person_search",
                "input": {"query": "Anna"},
                "output": {"results": []},
            },
            {
                "type": "tool_use",
                "id": "call_2",
                "name": "person_propose_create",
                "input": {"display_name": "Anna Doe"},
                "output": {"proposal_id": "p1"},
            },
        ]
    )
    asst, tool = out
    assert [b.id for b in asst.content if isinstance(b, ToolUseBlock)] == ["call_1", "call_2"]
    assert [b.tool_use_id for b in tool.content if isinstance(b, ToolResultBlock)] == [
        "call_1",
        "call_2",
    ]


@pytest.mark.unit
def test_splitter_missing_output_synthesizes_error_result() -> None:
    """A persisted tool_use whose output never landed (e.g., the turn
    crashed mid-stream) must still produce a paired tool_result so the
    Anthropic and OpenAI APIs do not see a dangling tool_use."""
    out = _assistant_messages_from_content(
        [
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "person_search",
                "input": {"query": "Anna"},
                "output": None,
                "is_error": False,
            }
        ]
    )
    assert len(out) == 2
    tool = out[1]
    result = tool.content[0]
    assert isinstance(result, ToolResultBlock)
    assert result.tool_use_id == "call_1"
    assert result.is_error is True
    assert "missing" in str(result.output).lower()


@pytest.mark.unit
def test_splitter_skips_proposals_summary_and_thinking_blocks() -> None:
    out = _assistant_messages_from_content(
        [
            {"type": "text", "text": "hi"},
            {"type": "thinking", "summary": "reasoning"},
            {"type": "proposals_summary", "proposal_ids": ["p1"]},
        ]
    )
    assert len(out) == 1
    assert len(out[0].content) == 1
    assert isinstance(out[0].content[0], TextBlock)
    assert out[0].content[0].text == "hi"


@pytest.mark.unit
def test_splitter_coerces_non_dict_input_to_empty_dict() -> None:
    """Tool-use input is supposed to be a JSON object once the agent loop
    parses it (chat.py:104-105). If a legacy or malformed row stores a
    string or null, the rehydrator must not feed that into a `ToolUseBlock`
    whose `input` is typed `dict[str, Any]`."""
    out = _assistant_messages_from_content(
        [
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "person_search",
                "input": "garbage",
                "output": {"results": []},
            }
        ]
    )
    use = out[0].content[0]
    assert isinstance(use, ToolUseBlock)
    assert use.input == {}


@pytest.mark.unit
def test_splitter_preserves_request_user_input_output_for_rehydration() -> None:
    """When an assistant turn ended with `request_user_input`, the persisted
    `tool_use` block carries the echoed question/options on `output`. The
    splitter must round-trip both sides so the frontend can lift the question
    back into the prompt card after a page reload, and so the next turn's
    LLM sees the question and the user's answer in context."""
    persisted = [
        {
            "type": "tool_use",
            "id": "call_q",
            "name": "request_user_input",
            "input": {"reason": "Which Anna do you mean?"},
            "output": {
                "acknowledged": True,
                "question": "Which Anna do you mean?",
                "options": ["Anna A", "Anna B"],
                "schema_hint": None,
            },
            "is_error": False,
        },
        {"type": "text", "text": "I need a clarification."},
    ]
    out = _assistant_messages_from_content(persisted)
    assert len(out) == 2
    asst, tool = out
    use = next(b for b in asst.content if isinstance(b, ToolUseBlock))
    assert use.name == "request_user_input"
    assert use.input == {"reason": "Which Anna do you mean?"}
    result = next(b for b in tool.content if isinstance(b, ToolResultBlock))
    assert result.tool_use_id == "call_q"
    assert isinstance(result.output, dict)
    assert result.output["question"] == "Which Anna do you mean?"
    assert result.output["options"] == ["Anna A", "Anna B"]
    assert result.is_error is False


@pytest.mark.unit
def test_splitter_pair_is_valid_llmmessage() -> None:
    """Sanity: the splitter returns real `LLMMessage` instances with
    matching roles, so the result can be appended directly to the message
    list `_history_messages` builds."""
    out = _assistant_messages_from_content(
        [
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "noop",
                "input": {},
                "output": {},
            }
        ]
    )
    assert all(isinstance(m, LLMMessage) for m in out)
    assert [m.role for m in out] == ["assistant", "tool"]


# --- _format_session_state -------------------------------------------------


def _row(
    *,
    action: ProposalAction = ProposalAction.create,
    target_type: SubjectType | None = SubjectType.person,
    payload: dict[str, object] | None = None,
    status: ProposalStatus = ProposalStatus.pending,
    target_id: UUID | None = None,
    proposal_id: UUID | None = None,
) -> _ProposalRow:
    return _ProposalRow(
        proposal_id=proposal_id or uuid4(),
        action=action,
        target_type=target_type,
        payload=payload or {},
        status=status,
        target_id=target_id,
    )


@pytest.mark.unit
def test_session_state_empty_returns_empty_string() -> None:
    assert _format_session_state([]) == ""


@pytest.mark.unit
def test_session_state_single_pending_person_renders_header_and_bullet() -> None:
    row = _row(payload={"display_name": "Anna Doe"})
    out = _format_session_state([row])
    lines = out.splitlines()
    assert lines[0] == _SESSION_STATE_HEADER
    assert len(lines) == 2
    bullet = lines[1]
    assert bullet.startswith(f"- proposal {row.proposal_id} | create person | ")
    assert "Anna Doe" in bullet
    assert bullet.endswith("status=pending")
    assert "->" not in bullet


@pytest.mark.unit
def test_session_state_approved_person_appends_target_id_arrow() -> None:
    target = uuid4()
    row = _row(
        payload={"display_name": "Anna Doe"},
        status=ProposalStatus.approved,
        target_id=target,
    )
    out = _format_session_state([row])
    bullet = out.splitlines()[1]
    assert bullet.endswith(f"status=approved -> person {target}")


@pytest.mark.unit
def test_session_state_preserves_input_order_across_statuses() -> None:
    a = _row(payload={"display_name": "A"}, status=ProposalStatus.approved, target_id=uuid4())
    b = _row(payload={"display_name": "B"})
    c = _row(payload={"display_name": "C"}, status=ProposalStatus.rejected)
    out = _format_session_state([a, b, c])
    bullets = [line for line in out.splitlines() if line.startswith("- proposal")]
    assert len(bullets) == 3
    assert "A" in bullets[0]
    assert "B" in bullets[1]
    assert "C" in bullets[2]


@pytest.mark.unit
def test_session_state_relationship_renders_type_and_endpoints() -> None:
    subj = uuid4()
    obj = uuid4()
    row = _row(
        target_type=SubjectType.relationship,
        payload={"type": "parent_of", "subject_id": str(subj), "object_id": str(obj)},
    )
    bullet = _format_session_state([row]).splitlines()[1]
    assert f"parent_of: {subj} -> {obj}" in bullet


@pytest.mark.unit
def test_session_state_event_renders_type_and_date() -> None:
    row = _row(
        target_type=SubjectType.event,
        payload={"type": "birth", "date_text": "April 15, 1932"},
    )
    bullet = _format_session_state([row]).splitlines()[1]
    assert "birth April 15, 1932" in bullet


@pytest.mark.unit
def test_session_state_place_renders_name() -> None:
    row = _row(target_type=SubjectType.place, payload={"name": "Boston, MA"})
    bullet = _format_session_state([row]).splitlines()[1]
    assert "Boston, MA" in bullet


@pytest.mark.unit
def test_session_state_source_create_uses_title_when_target_type_is_none() -> None:
    row = _row(target_type=None, payload={"title": "Vital records"})
    bullet = _format_session_state([row]).splitlines()[1]
    assert "Vital records" in bullet
    assert "| create - |" in bullet  # target_type=None renders as '-'


@pytest.mark.unit
def test_session_state_unknown_combination_falls_through_to_truncated_json() -> None:
    """An action/target combo we did not anticipate must not raise; it
    just renders as a short JSON dump of the payload so the agent still
    sees something. `(delete, event)` is not in the dispatch table."""
    row = _row(
        action=ProposalAction.delete,
        target_type=SubjectType.event,
        payload={"event_id": "abc-123"},
    )
    bullet = _format_session_state([row]).splitlines()[1]
    assert "abc-123" in bullet


@pytest.mark.unit
def test_session_state_person_update_lists_changed_fields() -> None:
    row = _row(
        action=ProposalAction.update,
        payload={"birth_text": "1900", "surname": "Doe"},
        target_id=uuid4(),
    )
    bullet = _format_session_state([row]).splitlines()[1]
    assert "update fields: birth_text, surname" in bullet
