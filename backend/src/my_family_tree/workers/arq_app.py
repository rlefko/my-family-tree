"""arq worker app. Run via `arq my_family_tree.workers.arq_app.WorkerSettings`."""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from my_family_tree.core.config import get_settings
from my_family_tree.core.errors import LLMProviderError
from my_family_tree.core.logging import configure_logging, get_logger
from my_family_tree.db.session import make_engine, make_sessionmaker
from my_family_tree.embed.client import build_embeddings_client
from my_family_tree.storage.s3 import build_object_store
from my_family_tree.workers.jobs.ingest_document import ingest_document

log = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_format=not settings.is_dev)
    engine = make_engine(settings)
    ctx["engine"] = engine
    ctx["session_factory"] = make_sessionmaker(engine)
    ctx["storage"] = build_object_store(settings.s3)
    try:
        ctx["embeddings_client"] = build_embeddings_client(settings.llm)
    except LLMProviderError as e:
        log.warning("worker.embeddings_unavailable", error=str(e))
        ctx["embeddings_client"] = None
    log.info("worker.startup", env=settings.app_env)


async def shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()
    log.info("worker.shutdown")


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings.from_dsn(settings.redis.url)


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ingest_document]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 8
    job_timeout = 60 * 30
    keep_result = 60 * 60
    health_check_interval = 30
