"""Alembic environment. Uses the sync psycopg driver because Alembic is sync.

The async engine elsewhere in the app is unrelated; migrations are operational
code, not request-path code, and a sync flow is simpler and safer here."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importing `models` registers every table on `SQLModel.metadata` (with our
# custom naming convention).
from my_family_tree.core.config import get_settings
from my_family_tree.db.base import metadata as target_metadata
from my_family_tree.models import enums  # noqa: F401  side-effect: enums available
from my_family_tree.models import (  # noqa: F401  side-effect: register tables
    AgentRun,
    Alias,
    Chunk,
    Claim,
    Conflict,
    ConflictClaim,
    Conversation,
    Document,
    DocumentText,
    Event,
    EventParticipant,
    FactProvenance,
    InferenceCache,
    Message,
    Person,
    Place,
    Proposal,
    Relationship,
    Source,
    Tree,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the sqlalchemy.url with the value from Settings (env-driven).
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.db.sync_url)


def run_migrations_offline() -> None:
    """Generate SQL without a live connection. Useful for diff inspection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
