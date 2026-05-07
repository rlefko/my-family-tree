"""Vision-LLM client. A small dedicated wrapper around the OpenAI Responses API
that takes a page image and returns a textual description of the visual content
(faces, signatures, stamps, handwritten margin notes, table headers, family-tree
diagrams, maps). Printed body text is left to OCR (`ingest/image.py`).

This intentionally does not go through the chat `LLMProvider` abstraction: the
chat path is text + tool_use only and shouldn't grow image branches it would
never use elsewhere."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, cast

from openai import AsyncOpenAI

from my_family_tree.core.config import Settings
from my_family_tree.core.errors import LLMProviderError
from my_family_tree.core.logging import get_logger

log = get_logger(__name__)


# Per-million-token rates for the default vision model. Update together with
# the model name when these drift; keeping them as module constants so cost
# tracking does not silently misreport.
GPT_4O_MINI_INPUT_USD_PER_M = 0.15
GPT_4O_MINI_OUTPUT_USD_PER_M = 0.60


VISION_PAGE_PROMPT = (
    "Describe the visual content of this document page in plain English. "
    "Focus on people in photos, signatures, stamps, seals, handwritten margin "
    "notes, tables (column headers and what each column represents), "
    "family-tree diagrams, and maps. Do not transcribe printed body text "
    "(handled separately by OCR). Output plain prose only, no JSON or "
    "Markdown. If the page has no visual elements worth describing beyond "
    "printed text, output an empty string."
)


@dataclass(slots=True)
class VisionDescription:
    text: str
    cost_usd: float
    model: str


class VisionClient:
    """Calls OpenAI Responses API with an image to get a description."""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self.model = model

    async def describe_page(
        self,
        image_bytes: bytes,
        *,
        prompt: str = VISION_PAGE_PROMPT,
        max_output_tokens: int = 800,
    ) -> VisionDescription:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:image/png;base64,{encoded}"
        # Responses API typed-dict union is too narrow for our shape, so we
        # build a plain list[dict] and pass it through; mirrors the chat
        # provider's `_to_openai_input` pattern.
        input_blocks: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [{"type": "input_image", "image_url": data_url}],
            },
        ]
        try:
            response = await self._client.responses.create(
                model=self.model,
                input=cast(Any, input_blocks),
                max_output_tokens=max_output_tokens,
            )
        except Exception as e:
            raise LLMProviderError(f"openai vision describe_page failed: {e}") from e

        text = _extract_output_text(response)
        cost = _estimate_cost(response)
        return VisionDescription(text=text, cost_usd=cost, model=self.model)


def build_vision_client(settings: Settings) -> VisionClient | None:
    """Returns `None` when vision is disabled or no key is configured. Callers
    treat `None` as "skip the vision step"."""
    if not settings.ocr.vision_fallback_enabled:
        return None
    if settings.ocr.vision_fallback_provider != "openai":
        # Anthropic vision integration not implemented yet; refuse rather than
        # silently fall through.
        log.warning(
            "vision.unsupported_provider",
            provider=settings.ocr.vision_fallback_provider,
        )
        return None
    if settings.llm.openai_api_key is None:
        return None
    client = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        timeout=settings.llm.request_timeout_s,
    )
    return VisionClient(client=client, model=settings.llm.vision_model)


def _extract_output_text(response: object) -> str:
    """Walk the Responses-API output structure for the assembled text. The SDK
    typically exposes `output_text` directly; fall back to manual traversal."""
    direct = getattr(response, "output_text", None)
    if isinstance(direct, str) and direct:
        return direct
    output = getattr(response, "output", None) or []
    parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None) or []
        for part in content:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _estimate_cost(response: object) -> float:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0.0
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    in_cost = (input_tokens / 1_000_000.0) * GPT_4O_MINI_INPUT_USD_PER_M
    out_cost = (output_tokens / 1_000_000.0) * GPT_4O_MINI_OUTPUT_USD_PER_M
    return in_cost + out_cost
