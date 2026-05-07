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
5. Add a unit test under `backend/tests/unit/test_mcp_registry.py` (just
   asserting the new tool is registered with the expected capability).
6. If the tool exposes new domain logic, add an integration test scaffold
   under `backend/tests/integration/mcp/`.
7. Reload the API: `make down && make up`. The tool is now available to the
   chat agent and to any external MCP client connected over HTTP.

NEVER add a tool that mutates a canonical entity directly. Always go through
`proposal`.
