# Architecture

A single Python package (`my_family_tree`) runs as three processes from one
container image, plus a Postgres + pgvector database, Redis, MinIO/S3, and a
Vite + React frontend.

```mermaid
flowchart LR
  user["User browser"] -->|HTTP / SSE| api["FastAPI (api)"]
  user -->|HTTP| frontend["Vite + React (frontend)"]
  cd["Claude Desktop"] -->|stdio MCP| mcpStdio["mcp (stdio mode)"]
  external["External MCP clients"] -->|Streamable HTTP| api
  api -->|in-process ToolHost| tools["MCP tool registry"]
  api -->|enqueue| redis[("Redis (arq)")]
  worker["arq worker"] -->|consume| redis
  worker -->|read/write| db[("Postgres 17 + pgvector")]
  api -->|read/write| db
  worker -->|raw + derived| s3[("S3 / MinIO")]
  api -->|presign| s3
  api -->|stream| openai["OpenAI Responses API"]
  api -->|stream| anthropic["Anthropic Messages API"]
```

## Process boundaries

| Process | Image | Command | Notes |
|---------|-------|---------|-------|
| api     | backend | `uvicorn ... --factory` | FastAPI; mounts MCP HTTP at `/mcp`; SSE chat |
| worker  | backend | `arq ... WorkerSettings` | ingestion, embeddings, claim extraction, deep research |
| mcp     | backend | `mft mcp --transport http` | dedicated MCP HTTP service for external clients (Claude Desktop, CI) |

The chat agent uses the **in-process `ToolHost`** to call MCP tool handlers
without serialization. The dedicated `mcp` service exists so external clients
can use the same registry over the standard transport. Same handler functions,
three ways in.

## Why this shape

- One image, three processes. We never have to keep `pip` deps in sync across
  separate codebases.
- Real MCP server, not a "MCP-style" abstraction. Claude Desktop and other
  external tools can drive the tree directly.
- Read freely, write only via proposals. The agent never mutates canonical
  entities; it creates `proposal` rows the user (or an explicit auto-approve
  policy) applies via the API.
