"""Document tools: list, get, presign."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from my_family_tree.core.errors import NotFoundError
from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import DocumentSummary
from my_family_tree.models.document import Document

registry = get_registry()


class DocumentListInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    kind: str | None = None
    status: str | None = None


class DocumentListOutput(BaseModel):
    items: list[DocumentSummary]
    total: int


@registry.tool(
    name="document_list",
    description="List uploaded documents. Filter by `kind` and/or `status`.",
    input_model=DocumentListInput,
    output_model=DocumentListOutput,
    capability=Capability.READ,
)
async def document_list(ctx: ToolContext, payload: DocumentListInput) -> DocumentListOutput:
    async with session_scope(ctx.session_factory) as session:
        stmt = select(Document).where(Document.tree_id == ctx.tree_id)
        if payload.kind:
            stmt = stmt.where(Document.kind == payload.kind)
        if payload.status:
            stmt = stmt.where(Document.status == payload.status)
        stmt = (
            stmt.order_by(Document.imported_at.desc()).limit(payload.limit).offset(payload.offset)
        )
        rows = (await session.execute(stmt)).scalars().all()
        items = [
            DocumentSummary(
                id=d.id,
                kind=d.kind.value,
                original_filename=d.original_filename,
                status=d.status.value,
                pages=d.pages,
                created_at=d.created_at,
            )
            for d in rows
        ]
        return DocumentListOutput(items=items, total=len(items))


class DocumentGetInput(BaseModel):
    document_id: UUID


class DocumentGetOutput(BaseModel):
    document: DocumentSummary
    storage_key: str
    storage_bucket: str
    sha256: str
    error: str | None = None


@registry.tool(
    name="document_get",
    description="Fetch a single document with storage location and processing status.",
    input_model=DocumentGetInput,
    output_model=DocumentGetOutput,
    capability=Capability.READ,
)
async def document_get(ctx: ToolContext, payload: DocumentGetInput) -> DocumentGetOutput:
    async with session_scope(ctx.session_factory) as session:
        doc = await session.get(Document, payload.document_id)
        if doc is None or doc.tree_id != ctx.tree_id:
            raise NotFoundError(f"document {payload.document_id} not found")
        return DocumentGetOutput(
            document=DocumentSummary(
                id=doc.id,
                kind=doc.kind.value,
                original_filename=doc.original_filename,
                status=doc.status.value,
                pages=doc.pages,
                created_at=doc.created_at,
            ),
            storage_key=doc.storage_key,
            storage_bucket=doc.storage_bucket,
            sha256=doc.sha256,
            error=doc.error,
        )
