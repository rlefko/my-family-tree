"""initial schema with extensions, enums, tables, and pgvector + FTS indexes

Revision ID: 0001_init
Revises:
Create Date: 2026-05-06 18:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from my_family_tree.db.base import metadata as target_metadata
from my_family_tree.models import enums  # noqa: F401  ensure enums imported
from my_family_tree.models import (  # noqa: F401  ensure tables registered
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
from my_family_tree.models.enums import ENUMS

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Extensions. `vector` provides the pgvector types and operators.
    #    `pg_trgm` provides trigram similarity for fuzzy name/place lookups.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. Postgres ENUM types. We create them explicitly (not via SQLAlchemy's
    #    PgEnum.create_type) so multiple tables can share the same type.
    bind = op.get_bind()
    for enum_name, enum_cls in ENUMS.items():
        values = ", ".join(f"'{m.value}'" for m in enum_cls)
        bind.execute(sa.text(f"CREATE TYPE {enum_name} AS ENUM ({values})"))

    # 3. Tables. Use SQLModel/SQLAlchemy metadata to emit the full CREATE TABLE
    #    set in dependency order. `target_metadata` already has every table
    #    registered (see imports above).
    target_metadata.create_all(bind=bind)

    # 4. Domain-specific indexes that are awkward to declare in SQLModel.

    # Trigram GIN indexes on names and normalized places.
    op.execute(
        "CREATE INDEX ix_person_display_name_trgm "
        "ON person USING gin (display_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_person_surname_trgm "
        "ON person USING gin (surname gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_place_normalized_trgm "
        "ON place USING gin (normalized gin_trgm_ops)"
    )

    # Generated tsvector column on chunk for hybrid (vector + FTS) retrieval.
    op.execute(
        "ALTER TABLE chunk ADD COLUMN tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )
    op.execute("CREATE INDEX ix_chunk_tsv ON chunk USING gin (tsv)")

    # HNSW on the half-precision vector column. Full-precision vector(3072)
    # cannot be HNSW-indexed (2000-dim cap); halfvec(3072) can.
    op.execute(
        "CREATE INDEX ix_chunk_embedding_half_hnsw "
        "ON chunk USING hnsw (embedding_half halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # Composite indexes that ride on common query shapes.
    op.execute("CREATE INDEX ix_chunk_document_seq ON chunk (document_id, seq)")
    op.execute(
        "CREATE INDEX ix_event_tree_type_date "
        "ON event (tree_id, type, date_min)"
    )
    op.execute(
        "CREATE INDEX ix_conflict_tree_status_severity "
        "ON conflict (tree_id, status, severity DESC)"
    )
    op.execute(
        "CREATE INDEX ix_fact_provenance_subject "
        "ON fact_provenance (subject_type, subject_id, predicate)"
    )

    # Unique-on-tree dedup for documents.
    op.execute(
        "CREATE UNIQUE INDEX uq_document_tree_sha256 "
        "ON document (tree_id, sha256)"
    )

    # Foreign keys for the composite-PK linking tables (couldn't be declared
    # via SQLModel because the primary key is the composite itself).
    op.execute(
        "ALTER TABLE event_participant "
        "ADD CONSTRAINT fk_event_participant_event_id_event "
        "FOREIGN KEY (event_id) REFERENCES event(id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE event_participant "
        "ADD CONSTRAINT fk_event_participant_person_id_person "
        "FOREIGN KEY (person_id) REFERENCES person(id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE conflict_claim "
        "ADD CONSTRAINT fk_conflict_claim_conflict_id_conflict "
        "FOREIGN KEY (conflict_id) REFERENCES conflict(id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE conflict_claim "
        "ADD CONSTRAINT fk_conflict_claim_claim_id_claim "
        "FOREIGN KEY (claim_id) REFERENCES claim(id) ON DELETE CASCADE"
    )


def downgrade() -> None:
    bind = op.get_bind()

    # Composite-PK FKs.
    for stmt in (
        "ALTER TABLE conflict_claim DROP CONSTRAINT IF EXISTS fk_conflict_claim_claim_id_claim",
        (
            "ALTER TABLE conflict_claim DROP CONSTRAINT IF EXISTS "
            "fk_conflict_claim_conflict_id_conflict"
        ),
        (
            "ALTER TABLE event_participant DROP CONSTRAINT IF EXISTS "
            "fk_event_participant_person_id_person"
        ),
        (
            "ALTER TABLE event_participant DROP CONSTRAINT IF EXISTS "
            "fk_event_participant_event_id_event"
        ),
    ):
        op.execute(stmt)

    target_metadata.drop_all(bind=bind)

    for enum_name in ENUMS:
        bind.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))

    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
