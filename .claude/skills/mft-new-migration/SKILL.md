---
name: mft-new-migration
description: Generate and hand-review a new Alembic migration after editing SQLModel tables.
---

Use when the user asks to add or change a database table.

1. Edit the SQLModel definition under `backend/src/my_family_tree/models/`.
   If you added a new aggregate, also add it to `models/__init__.py`.
2. Run `make migration M="add <thing>"`. This calls
   `alembic revision --autogenerate`.
3. Hand-review the generated migration:
   - Confirm enum types are referenced via `models.enums` (don't recreate them).
   - Confirm vector columns use `Vector(N)` and `HALFVEC(N)` from `db.types`.
   - For HNSW or trigram indexes, add `op.execute("CREATE INDEX ...")` because
     autogenerate doesn't emit them.
   - For composite-PK tables (event_participant, conflict_claim), make sure
     the FK constraints are declared via `op.execute("ALTER TABLE ...")` since
     SQLModel can't express them inline.
4. `make migrate` to apply.
5. If your change is destructive (dropping a column, narrowing a type),
   document the intentional drop in the migration's docstring and add a note
   to the PR body.
