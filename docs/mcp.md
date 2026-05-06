# MCP server

The MCP server is built with the official `mcp` Python SDK and exposes the
same tool registry over both stdio (for Claude Desktop) and Streamable HTTP
(for the web app and external clients).

## Code layout

- `backend/src/my_family_tree/mcp/registry.py` — single source of truth for
  tools. Tools register themselves at import time via `@registry.tool(...)`.
- `backend/src/my_family_tree/mcp/host.py` — in-process `ToolHost` used by the
  chat agent (no transport overhead).
- `backend/src/my_family_tree/mcp/server.py` — official-SDK server wired to
  the same registry; runs in stdio or HTTP mode.
- `backend/src/my_family_tree/mcp/tools/` — per-domain tool modules.

## Capabilities

```python
class Capability(Flag):
    READ          # all read tools
    PROPOSE       # propose-write tools that produce proposals
    WEB           # web_search, web_fetch
    TRIVIAL_WRITE # note_append, conversation_set_title (commit directly)
    PRIVILEGED    # API-only; not exposed via MCP
```

The chat agent runs with `READ | PROPOSE | TRIVIAL_WRITE | WEB`. The deep
research subagent gets the same set with bigger budgets. The MCP HTTP service
exposes only `READ` by default for external clients.

## Adding a tool

```python
from pydantic import BaseModel
from my_family_tree.mcp.registry import Capability, get_registry

registry = get_registry()

class FooInput(BaseModel):
    bar: str

class FooOutput(BaseModel):
    result: str

@registry.tool(
    name="foo_search",
    description="Search foo bars",
    input_model=FooInput,
    output_model=FooOutput,
    capability=Capability.READ,
)
async def foo_search(ctx, payload: FooInput) -> FooOutput:
    return FooOutput(result=f"hello {payload.bar}")
```

Add the module name to `mcp/tools/__init__.py` so the import side effect
fires.

## Running

- stdio (Claude Desktop): `make mcp-stdio`
- HTTP (default in compose): `make up && curl http://localhost:8765/healthz`
- Behind ALB in prod, sticky sessions are required because Streamable HTTP
  holds session state per client. The `alb` Terraform module already enables
  `lb_cookie` stickiness on the mcp target group; do not disable it.
