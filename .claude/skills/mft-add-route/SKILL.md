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
   `SessionDep`, `StorageDep`, `LLMDep`, `SettingsDep`. Don't add a dep to
   the signature you don't actually use; FastAPI doesn't need it and a
   `del settings` smell-test will surface it later.
4. **For endpoints that mutate canonical entities (person/relationship/
   event/place/source/claim), route through the proposal applier rather
   than writing to tables directly.** The pattern (see `update_person`,
   `delete_relationship`, `add_relationship`, `add_event` in
   `routers/people.py`) is:
   - construct a `Proposal(... status=ProposalStatus.pending)`, `session.add`
     it, then `await session.flush()` to get an id;
   - `target_id = await apply_proposal(session, proposal, actor="user")`;
   - mark it approved in place: `proposal.status = ProposalStatus.approved`,
     `proposal.target_id = target_id`, `proposal.approved_at = utcnow()`,
     `proposal.applied_at = utcnow()`, `proposal.approved_by = "user"`,
     then flush again.
   This keeps the audit trail (synthetic `Source` + `Claim` +
   `FactProvenance`) consistent with the chat-driven path. Don't reinvent
   the dedup / mirroring / claim-writing logic in the router.
5. Register the router in `backend/src/my_family_tree/api/app.py` with the
   `/api/v1` prefix and a sensible tag.
6. Add an integration test under `backend/tests/integration/api/`.
7. Run `make openapi && make gen-types` to refresh the typed frontend client.
   CI verifies the generated file matches what the running api emits, so
   forgetting this step makes CI fail.
8. If the new endpoint exposes a new resource, add a hook under
   `frontend/src/api/endpoints/` and use it from a new or existing route in
   `frontend/src/routes/`.
