---
name: mft-add-route
description: Add a new FastAPI endpoint with router, schema, integration test scaffold, and a reminder to regenerate frontend types.
---

Use when the user asks to add a new API endpoint.

1. Pick a router under `backend/src/my_family_tree/api/routers/` or create a
   new one (e.g. `routers/places.py`).
2. Define request/response Pydantic models inline or under `schemas/` if
   reused.
3. Implement the handler. Use the dependency aliases from `api/deps.py`:
   `SessionDep`, `StorageDep`, `LLMDep`, `SettingsDep`.
4. Register the router in `backend/src/my_family_tree/api/app.py` with the
   `/api/v1` prefix and a sensible tag.
5. Add an integration test under `backend/tests/integration/api/`.
6. Run `make openapi && make gen-types` to refresh the typed frontend client.
   CI verifies the generated file matches what the running api emits, so
   forgetting this step makes CI fail.
7. If the new endpoint exposes a new resource, add a hook under
   `frontend/src/api/endpoints/` and use it from a new or existing route in
   `frontend/src/routes/`.
