"""Tests for `ImageBlock` conversion in the OpenAI and Anthropic adapters.

The chat path now sends user-attached images inline as `ImageBlock`. Each
provider's `_to_*` translator must emit the provider-specific image shape
without disturbing existing text and tool plumbing."""

from __future__ import annotations

import pytest

from my_family_tree.llm.anthropic_provider import _to_anthropic_messages
from my_family_tree.llm.base import ImageBlock, Message, TextBlock
from my_family_tree.llm.openai_provider import _to_openai_input


@pytest.mark.unit
def test_openai_input_emits_input_image_as_data_url_for_user_image() -> None:
    messages = [
        Message(
            role="user",
            content=[
                TextBlock(type="text", text="what does this show?"),
                ImageBlock(type="image", media_type="image/png", data_b64="AAA"),
            ],
        ),
    ]
    out = _to_openai_input(None, messages)
    assert len(out) == 1
    user_item = out[0]
    assert user_item["role"] == "user"
    parts = user_item["content"]
    assert parts[0] == {"type": "input_text", "text": "what does this show?"}
    assert parts[1] == {
        "type": "input_image",
        "image_url": "data:image/png;base64,AAA",
    }


@pytest.mark.unit
def test_openai_input_skips_image_block_on_assistant_role() -> None:
    """We never have the assistant emit images, so a stray `ImageBlock` on
    a non-user message must be dropped rather than fed back to the API as an
    invalid `output_text` part."""
    messages = [
        Message(
            role="assistant",
            content=[
                TextBlock(type="text", text="here you go"),
                ImageBlock(type="image", media_type="image/png", data_b64="ZZZ"),
            ],
        ),
    ]
    out = _to_openai_input(None, messages)
    assert len(out) == 1
    parts = out[0]["content"]
    assert all(p["type"] != "input_image" for p in parts)
    assert parts == [{"type": "output_text", "text": "here you go"}]


@pytest.mark.unit
def test_anthropic_messages_emit_base64_image_source_for_user_image() -> None:
    messages = [
        Message(
            role="user",
            content=[
                TextBlock(type="text", text="what does this show?"),
                ImageBlock(type="image", media_type="image/jpeg", data_b64="BBB"),
            ],
        ),
    ]
    out = _to_anthropic_messages(messages)
    assert len(out) == 1
    msg = out[0]
    assert msg["role"] == "user"
    blocks = msg["content"]
    assert blocks[0] == {"type": "text", "text": "what does this show?"}
    assert blocks[1] == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": "BBB",
        },
    }


@pytest.mark.unit
def test_anthropic_messages_drop_image_on_assistant_role() -> None:
    messages = [
        Message(
            role="assistant",
            content=[
                TextBlock(type="text", text="here you go"),
                ImageBlock(type="image", media_type="image/png", data_b64="QQQ"),
            ],
        ),
    ]
    out = _to_anthropic_messages(messages)
    assert len(out) == 1
    blocks = out[0]["content"]
    assert all(b["type"] != "image" for b in blocks)
    assert blocks == [{"type": "text", "text": "here you go"}]
