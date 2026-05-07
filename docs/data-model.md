# Data model

The schema lives at `backend/src/my_family_tree/models/`. Conventions:

- All primary keys are `UUID` generated as **UUIDv7** via `uuid_utils.uuid7()`
  for time-ordered B-tree locality on hot tables.
- Every domain row carries `tree_id` even though v1 is single-user.
- Soft delete via `deleted_at` (default null).
- Postgres ENUMs (`models/enums.py`) are created in the initial migration so
  multiple tables can share the same type.
- Date uncertainty is an inline triple on rows that need it: `date_text`
  (verbatim), `date_min`, `date_max`, `date_precision`, `date_circa`.
- Vector columns: full `vector(3072)` plus an indexable `halfvec(3072)`
  (full-precision cannot be HNSW-indexed; halfvec can).

## Rule the LLM lives by

Claims are the only thing the LLM writes during ingestion. A claim is an
attributable assertion with confidence and a chunk-level provenance pointer.
Updates to canonical entities (Person, Event, Relationship) only happen when a
claim is **accepted**, driven by an approved `proposal`. Acceptance writes a
`fact_provenance` row so we can answer "why do we believe X?" instantly.

## Aggregate map

```mermaid
erDiagram
  TREE ||--o{ PERSON : contains
  TREE ||--o{ PLACE : contains
  TREE ||--o{ EVENT : contains
  TREE ||--o{ DOCUMENT : contains
  PERSON ||--o{ ALIAS : has
  PERSON ||--o{ RELATIONSHIP : subject
  EVENT ||--o{ EVENT_PARTICIPANT : has
  PERSON ||--o{ EVENT_PARTICIPANT : in
  DOCUMENT ||--o{ DOCUMENT_TEXT : has
  DOCUMENT ||--o{ CHUNK : has
  CHUNK ||--o{ CLAIM : evidence
  SOURCE ||--o{ CLAIM : cited_by
  CLAIM ||--o{ FACT_PROVENANCE : proves
  CLAIM ||--o{ CONFLICT_CLAIM : in
  CONFLICT ||--o{ CONFLICT_CLAIM : has
  PROPOSAL ||--|| AGENT_RUN : produced_by
  CONVERSATION ||--o{ MESSAGE : has
  AGENT_RUN ||--o{ MESSAGE : recorded_in
```

See `models/__init__.py` for the canonical list of tables.
