"""LLM-based claim extraction from chunks. Uses the configured provider with
structured outputs (JSON schema) so the response shape is deterministic."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from my_family_tree.core.logging import get_logger
from my_family_tree.extract.prompts import (
    CLAIM_EXTRACTION_PROMPT_VERSION,
    CLAIM_EXTRACTION_SYSTEM,
)
from my_family_tree.llm.base import LLMProvider, Message, ReasoningConfig, TextBlock

log = get_logger(__name__)


class ExtractedClaim(BaseModel):
    kind: str
    subject_hint: str
    predicate: str
    object: Any = Field(default_factory=dict)
    confidence: int = 50
    rationale: str = ""
    span_start: int = 0
    span_end: int = 0


class ExtractedClaims(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)


def cache_key(content: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"|")
    h.update(CLAIM_EXTRACTION_PROMPT_VERSION.encode())
    h.update(b"|")
    h.update(content.encode("utf-8", errors="replace"))
    return h.hexdigest()


async def extract_claims_from_chunk(
    *,
    provider: LLMProvider,
    model: str,
    content: str,
    chunk_id: UUID | None = None,
) -> ExtractedClaims:
    """Run claim extraction on a single chunk's content. Caller is responsible
    for caching against `cache_key()`."""
    del chunk_id  # caller correlates; not needed in the prompt
    messages = [
        Message(role="user", content=[TextBlock(type="text", text=content)]),
    ]
    result = await provider.complete(
        model=model,
        system=CLAIM_EXTRACTION_SYSTEM,
        messages=messages,
        max_tokens=2000,
        reasoning=ReasoningConfig(effort="high"),
    )
    text = "".join(b.text for b in result.blocks if isinstance(b, TextBlock))
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("extract.parse_failed", error=str(e), text_head=text[:200])
        return ExtractedClaims()
    return ExtractedClaims.model_validate(payload)
