"""`external_index_url` MCP tool.

Fetches a URL, normalizes the body to plain text, and persists it as a
`Document(kind=web)` plus `Source(kind=web)` so the page becomes citable
and vector-searchable from then on. Idempotent on `(tree_id, sha256)`:
re-running on the same URL returns the existing document without
re-fetching the body."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry

registry = get_registry()


class ExternalIndexUrlInput(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    title: str | None = Field(default=None, max_length=500)


class ExternalIndexUrlOutput(BaseModel):
    document_id: UUID
    source_id: UUID
    chunk_count: int
    embedded: bool
    dedup_hit: bool


@registry.tool(
    name="external_index_url",
    description=(
        "Fetch a URL and add its plain-text content to the knowledge base as "
        "a citable Document and Source. Returns a `document_id` you can cite "
        "in proposals, and `embedded=true` once chunks are vector-indexed. "
        "Re-calling on the same URL is idempotent (`dedup_hit=true`)."
    ),
    input_model=ExternalIndexUrlInput,
    output_model=ExternalIndexUrlOutput,
    capability=Capability.WEB | Capability.TRIVIAL_WRITE,
    is_read_only=False,
)
async def external_index_url(
    ctx: ToolContext, payload: ExternalIndexUrlInput
) -> ExternalIndexUrlOutput:
    if ctx.external_ingest is None:
        raise ExternalProviderError(
            "external_index_url requires a configured ingest service (storage + db)"
        )
    result = await ctx.external_ingest.ingest(
        tree_id=ctx.tree_id, url=payload.url, title=payload.title
    )
    return ExternalIndexUrlOutput(
        document_id=result.document_id,
        source_id=result.source_id,
        chunk_count=result.chunk_count,
        embedded=result.embedded,
        dedup_hit=result.dedup_hit,
    )
