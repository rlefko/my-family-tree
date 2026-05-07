---
name: mft-add-mcp-tool
description: Add a new MCP tool to the shared registry so the chat agent and external MCP clients can both call it.
---

Use when the user asks to add a new MCP tool.

1. Decide the right module under `backend/src/my_family_tree/mcp/tools/`. If
   the tool is read-only on persons, it goes in `persons.py`; on documents,
   `documents.py`; etc. Create a new module for a new domain.
2. Define `<Name>Input` and `<Name>Output` Pydantic models. Keep input schemas
   minimal and well-described so the LLM gets a tight tool catalog.
3. Decorate the handler with `@registry.tool(...)` from
   `my_family_tree.mcp.registry`. Pick the right `Capability`:
   - `READ` for everything that doesn't mutate canonical entities.
   - `PROPOSE` for write tools that emit `proposal` rows (set
     `is_read_only=False` and have the body call into `mcp/tools/proposals.py`
     helpers).
   - `WEB` for web_search/web_fetch wrappers.
   - `TRIVIAL_WRITE` for note_append, conversation_set_title, etc.
4. If you created a new module, add it to `mcp/tools/__init__.py`'s import
   list so the import-time registration fires.
5. **For PROPOSE tools, also wire the applier.** A queued proposal is inert
   until `services/proposal_apply.py` knows how to apply it. Add (or extend)
   a branch in the `apply_proposal` dispatch for the `(action, target_type)`
   pair you emit and write a `_apply_<action>_<target_type>` handler. Reuse:
   - `SYMMETRIC_RELS` for spouse/sibling/partner mirroring.
   - `normalize_place_name` and `_find_existing_place` for place dedup.
   - `_resolve_person_ref` for inputs that may be a canonical `person.id` or
     a still-pending `proposal.id` (the chat agent wires edges to people
     before the user has approved them).
   - `get_or_create_chat_source` + `write_user_claims` to materialize the
     synthetic `Source(kind=user_assertion)` and per-fact `Claim` rows so
     provenance is preserved automatically. Use `_supersede_claims` first
     when an update overrides previously-accepted facts.
   - `_parse_date` for any date-text field.
   Without an applier branch, `apply_proposal` raises
   `"no applier wired for (action=..., target_type=...)"` on approve.
6. Add a unit test under `backend/tests/unit/test_mcp_registry.py` (just
   asserting the new tool is registered with the expected capability).
7. If the tool exposes new domain logic, add an integration test scaffold
   under `backend/tests/integration/mcp/`.
8. Reload the API: `make down && make up`. The tool is now available to the
   chat agent and to any external MCP client connected over HTTP.

NEVER add a tool that mutates a canonical entity directly. Always go through
`proposal`.
