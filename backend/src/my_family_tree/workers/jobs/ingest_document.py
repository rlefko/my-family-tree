"""arq job: ingest a single document through the pipeline."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from my_family_tree.core.logging import get_logger
from my_family_tree.ingest.pipeline import PipelineDeps, run_pipeline

log = get_logger(__name__)


async def ingest_document(ctx: dict[str, Any], document_id: str) -> dict[str, Any]:
    doc_uuid = UUID(document_id)
    log.info("ingest.start", document_id=document_id)
    deps = PipelineDeps(embeddings=ctx.get("embeddings_client"))
    state = await run_pipeline(
        ctx["session_factory"],
        doc_uuid,
        ctx["storage"],
        deps,
    )
    log.info("ingest.done", document_id=document_id, steps=state.completed_steps)
    return {"document_id": document_id, "completed_steps": state.completed_steps}
