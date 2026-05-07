"""Embeddings client and batched runner."""

from my_family_tree.embed.client import EmbeddingsClient, build_embeddings_client
from my_family_tree.embed.runner import embed_chunks_in_batches

__all__ = ["EmbeddingsClient", "build_embeddings_client", "embed_chunks_in_batches"]
