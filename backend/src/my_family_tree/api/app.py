"""FastAPI app factory + lifespan. The MCP Streamable HTTP transport is
mounted at `/mcp` so external MCP clients can connect to the same process."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from my_family_tree.api.errors import register_exception_handlers
from my_family_tree.api.middleware import RequestContextMiddleware
from my_family_tree.api.routers import (
    chat,
    conflicts,
    documents,
    health,
    people,
    proposals,
    tree,
)
from my_family_tree.core.config import get_settings
from my_family_tree.core.logging import configure_logging, get_logger
from my_family_tree.db.session import make_engine, make_sessionmaker
from my_family_tree.llm.registry import build_registry
from my_family_tree.storage.s3 import build_object_store

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_format=not settings.is_dev)
    engine = make_engine(settings)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_sessionmaker(engine)
    app.state.storage = build_object_store(settings.s3)
    app.state.llm = build_registry(settings.llm)
    log.info("api.startup", env=settings.app_env)
    try:
        yield
    finally:
        await engine.dispose()
        log.info("api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    app.include_router(health.router, tags=["health"])
    app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
    app.include_router(people.router, prefix="/api/v1", tags=["people"])
    app.include_router(conflicts.router, prefix="/api/v1", tags=["conflicts"])
    app.include_router(proposals.router, prefix="/api/v1", tags=["proposals"])
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(tree.router, prefix="/api/v1", tags=["tree"])

    return app
