"""Embeddings client. OpenAI text-embedding-3-large (3072 dims) is the default;
the interface is small enough that swapping providers later is mechanical."""

from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI

from my_family_tree.core.config import LLMSettings
from my_family_tree.core.errors import LLMProviderError
from my_family_tree.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class EmbeddingsClient:
    client: AsyncOpenAI
    model: str
    dims: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            resp = await self.client.embeddings.create(model=self.model, input=texts)
        except Exception as e:
            raise LLMProviderError(f"openai embeddings failed: {e}") from e
        return [d.embedding for d in resp.data]


def build_embeddings_client(settings: LLMSettings) -> EmbeddingsClient:
    if settings.openai_api_key is None:
        raise LLMProviderError("OPENAI_API_KEY is required for embeddings (v1)")
    return EmbeddingsClient(
        client=AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.request_timeout_s,
        ),
        model=settings.embedding_model,
        dims=settings.embedding_dims,
    )
