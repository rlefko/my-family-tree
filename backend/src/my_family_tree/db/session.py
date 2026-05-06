"""Async SQLAlchemy engine + sessionmaker, lifecycle-managed by the FastAPI app.

Use `get_session()` (FastAPI dep) inside request handlers and `session_factory()`
(context manager) inside arq jobs and CLI entry points.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from my_family_tree.core.config import Settings


def make_engine(settings: Settings) -> AsyncEngine:
    """Build an async engine. Pool sizing is conservative; tune via Settings."""
    return create_async_engine(
        settings.db.async_url,
        pool_size=settings.db.pool_size,
        max_overflow=settings.db.max_overflow,
        pool_pre_ping=True,
        echo=settings.db.echo,
        future=True,
    )


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Context-managed transactional session. Commits on exit, rolls back on raise."""
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
