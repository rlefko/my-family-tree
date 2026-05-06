"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_family_tree.core.config import Settings, get_settings
from my_family_tree.llm.registry import ProviderRegistry
from my_family_tree.storage.s3 import ObjectStore


def settings_dep() -> Settings:
    return get_settings()


def session_factory_dep(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory  # type: ignore[no-any-return]


async def session_dep(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(session_factory_dep)],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def storage_dep(request: Request) -> ObjectStore:
    return request.app.state.storage  # type: ignore[no-any-return]


def llm_registry_dep(request: Request) -> ProviderRegistry:
    return request.app.state.llm  # type: ignore[no-any-return]


SessionDep = Annotated[AsyncSession, Depends(session_dep)]
StorageDep = Annotated[ObjectStore, Depends(storage_dep)]
LLMDep = Annotated[ProviderRegistry, Depends(llm_registry_dep)]
SettingsDep = Annotated[Settings, Depends(settings_dep)]
