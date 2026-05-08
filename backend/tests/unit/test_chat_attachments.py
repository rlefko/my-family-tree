"""Pure-function tests for the chat router's attachment helpers.

These cover suffix construction, structured content_json round-trip, and the
inline-image budget logic without spinning up a request or a database. The
DB-driven `_history_messages` and `_build_messages` paths are exercised in
integration tests when those land."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from my_family_tree.api.routers.chat import (
    ChatAttachmentInput,
    ChatRequest,
    _attachment_suffix,
    _AttachmentRef,
    _content_blocks_for_user_turn,
    _ResolvedAttachment,
    _user_attachment_doc_ids,
    _user_content_json,
    _user_text_from_blocks,
)
from my_family_tree.llm.base import ImageBlock, TextBlock


def _ref(doc_id: UUID, *, kind: str = "image", filename: str | None = "tree.png") -> _AttachmentRef:
    return _AttachmentRef(
        document_id=doc_id,
        filename=filename,
        kind=kind,
        mime_type="image/png" if kind == "image" else "application/pdf",
    )


@pytest.mark.unit
def test_attachment_suffix_lists_each_ref_with_kind_and_id() -> None:
    a = uuid4()
    b = uuid4()
    refs = [
        _ref(a, kind="image", filename="tree.png"),
        _ref(b, kind="pdf_text", filename="src.pdf"),
    ]
    suffix = _attachment_suffix(refs)
    assert suffix.startswith("[Attached: ")
    assert suffix.endswith("]")
    assert f"tree.png (image, id: {a})" in suffix
    assert f"src.pdf (pdf_text, id: {b})" in suffix


@pytest.mark.unit
def test_attachment_suffix_is_empty_when_no_refs() -> None:
    assert _attachment_suffix([]) == ""


@pytest.mark.unit
def test_content_blocks_emit_text_then_images_in_order() -> None:
    a = uuid4()
    b = uuid4()
    resolved = [
        _ResolvedAttachment(
            ref=_ref(a),
            image=ImageBlock(type="image", media_type="image/png", data_b64="AAA"),
        ),
        _ResolvedAttachment(
            ref=_ref(b),
            image=ImageBlock(type="image", media_type="image/png", data_b64="BBB"),
        ),
    ]
    blocks = _content_blocks_for_user_turn("describe this", resolved)
    # First block is text with the suffix appended; remaining blocks are images.
    assert isinstance(blocks[0], TextBlock)
    assert "describe this" in blocks[0].text
    assert "[Attached: " in blocks[0].text
    assert isinstance(blocks[1], ImageBlock)
    assert blocks[1].data_b64 == "AAA"
    assert isinstance(blocks[2], ImageBlock)
    assert blocks[2].data_b64 == "BBB"


@pytest.mark.unit
def test_content_blocks_drop_attachments_with_no_inlined_image() -> None:
    """A non-image attachment (or one whose bytes failed to load) must still
    show up in the bracket suffix so the agent can `hybrid_search` it, but
    no `ImageBlock` is emitted."""
    a = uuid4()
    resolved = [
        _ResolvedAttachment(ref=_ref(a, kind="pdf_text", filename="src.pdf"), image=None),
    ]
    blocks = _content_blocks_for_user_turn("summarize this", resolved)
    assert len(blocks) == 1
    assert isinstance(blocks[0], TextBlock)
    assert "src.pdf" in blocks[0].text
    assert "pdf_text" in blocks[0].text


@pytest.mark.unit
def test_content_blocks_for_attachment_only_message_drops_text() -> None:
    a = uuid4()
    resolved = [
        _ResolvedAttachment(
            ref=_ref(a),
            image=ImageBlock(type="image", media_type="image/png", data_b64="AAA"),
        ),
    ]
    blocks = _content_blocks_for_user_turn("", resolved)
    # No user text means the suffix becomes the leading TextBlock content; we
    # still emit it because it carries the document id the agent might want.
    assert isinstance(blocks[0], TextBlock)
    assert blocks[0].text.startswith("[Attached: ")
    assert isinstance(blocks[1], ImageBlock)


@pytest.mark.unit
def test_user_content_json_round_trips_attachment_block() -> None:
    a = uuid4()
    req = ChatRequest(
        tree_id=uuid4(),
        message="hi",
        attachments=[ChatAttachmentInput(document_id=a)],
    )
    resolved = [
        _ResolvedAttachment(
            ref=_ref(a, kind="image", filename="tree.png"),
            image=ImageBlock(type="image", media_type="image/png", data_b64="AAA"),
        ),
    ]
    payload = _user_content_json(req, resolved)
    assert payload[0] == {"type": "text", "text": "hi"}
    assert payload[1] == {
        "type": "attachment",
        "document_id": str(a),
        "filename": "tree.png",
        "mime_type": "image/png",
        "kind": "image",
    }
    # _user_attachment_doc_ids should pull the same id back out.
    assert _user_attachment_doc_ids(payload) == [a]


@pytest.mark.unit
def test_user_text_from_blocks_concatenates_text_only() -> None:
    blocks = [
        {"type": "text", "text": "hello "},
        {"type": "attachment", "document_id": str(uuid4()), "filename": "x"},
        {"type": "text", "text": "world"},
    ]
    assert _user_text_from_blocks(blocks) == "hello world"


@pytest.mark.unit
def test_user_attachment_doc_ids_skips_invalid_uuids() -> None:
    a = uuid4()
    blocks = [
        {"type": "attachment", "document_id": str(a)},
        {"type": "attachment", "document_id": "not-a-uuid"},
        {"type": "attachment"},
    ]
    assert _user_attachment_doc_ids(blocks) == [a]
