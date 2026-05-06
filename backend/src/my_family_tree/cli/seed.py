"""Demo seed data. v1 stub: creates a single empty tree row so the API has
something to scope to. Real seed fixtures (a small synthetic family) come in
a follow-up."""

from __future__ import annotations

from sqlalchemy import select

from my_family_tree.core.config import get_settings
from my_family_tree.core.logging import configure_logging, get_logger
from my_family_tree.db.session import make_engine, make_sessionmaker, session_scope
from my_family_tree.models.tree import Tree

log = get_logger(__name__)


async def run_seed() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_format=not settings.is_dev)
    engine = make_engine(settings)
    factory = make_sessionmaker(engine)
    try:
        async with session_scope(factory) as session:
            existing = (
                await session.execute(select(Tree).where(Tree.name == "Default Tree"))
            ).scalar_one_or_none()
            if existing is not None:
                log.info(
                    "seed.skip",
                    reason="default tree already exists",
                    tree_id=str(existing.id),
                )
                return
            tree = Tree(name="Default Tree", description="Auto-created on first seed")
            session.add(tree)
            await session.flush()
            log.info("seed.created", tree_id=str(tree.id), name=tree.name)
    finally:
        await engine.dispose()
