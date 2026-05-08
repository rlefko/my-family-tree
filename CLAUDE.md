# Claude Code conventions for My Family Tree

This file briefs every Claude Code session that opens this repo. Keep it tight and current.

## Project

A personal genealogy research workbench. Upload documents, extract evidence, query the family tree via natural language, resolve conflicts, run deep research. Single-user, no auth. The chat agent talks to a real MCP server (stdio + Streamable HTTP) that exposes read tools and propose-write tools. Canonical writes only happen when the user approves a `proposal` row.

## Stack (locked in)

- **Backend**: Python 3.14, FastAPI, SQLAlchemy 2 + SQLModel, Alembic, Pydantic, arq
- **DB**: Postgres 17 with `pgvector` (HNSW on `halfvec(3072)`), `pg_trgm`, GIN-FTS
- **Storage**: MinIO locally, S3 in prod (boto3 with path-style)
- **LLMs**: direct OpenAI + Anthropic SDKs, no LiteLLM. Default `gpt-5` with `reasoning.effort="medium"`.
- **Embeddings**: `text-embedding-3-large` (3072 dims)
- **MCP**: official `mcp` Python SDK; stdio + Streamable HTTP
- **Frontend**: TypeScript, React 18, Vite, Tailwind v4, shadcn/ui, TanStack Router (file-based) + Query, react-hook-form + zod
- **Tooling**: `uv`, `yarn`, `ruff` (backend lint+format), `ty` (backend typecheck), `pytest` + `testcontainers`, `oxlint` (frontend lint), `tsgo` (frontend typecheck via `@typescript/native-preview`), `prettier` (frontend format), `vitest`
- **Infra**: Terraform on AWS (VPC, ECS Fargate, RDS, S3, ALB, Secrets Manager)

## Commands

| Make target                                                                | What it does                                                  |
| -------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `make bootstrap`                                                           | Tool checks, `uv sync`, `yarn install`, `pre-commit install`  |
| `make up` / `make down` / `make nuke` / `make restart`                     | Docker compose up / down / down -v / restart                  |
| `make build` / `make build-backend` / `make build-frontend`                | Rebuild docker images (use after Dockerfile changes)          |
| `make deps` / `make deps-backend` / `make deps-frontend`                   | Sync deps inside running containers (uv sync / yarn install)  |
| `make deps-fresh`                                                          | Drop venv + node_modules volumes and reinstall (db preserved) |
| `make logs` / `make ps`                                                    | Follow logs / list services                                   |
| `make shell-api` / `make shell-db`                                         | Bash in api / `psql` in db                                    |
| `make migrate` / `make migration M="..."`                                  | Apply / autogenerate Alembic migration                        |
| `make seed`                                                                | Load demo tree data                                           |
| `make test` / `make test-backend` / `make test-frontend` / `make test-int` | Run tests                                                     |
| `make lint` / `make format` / `make typecheck`                             | Lint / format / typecheck (back + front)                      |
| `make openapi` / `make gen-types`                                          | Dump OpenAPI JSON / regen frontend types                      |
| `make mcp-stdio`                                                           | Run MCP server in stdio mode (for Claude Desktop)             |
| `make tf-fmt` / `make tf-validate` / `make tf-plan-dev`                    | Terraform helpers (no apply)                                  |

### When dependencies change

| Change                                               | Run                                                                    |
| ---------------------------------------------------- | ---------------------------------------------------------------------- |
| Added/removed a package in `pyproject.toml`          | `cd backend && uv lock`, then `make deps-backend`                      |
| Added/removed a package in `package.json`            | `cd frontend && yarn install`, then `make deps-frontend`               |
| Edited `backend/Dockerfile` or `frontend/Dockerfile` | `make build`                                                           |
| Native extension trouble or weird state              | `make deps-fresh` (drops venv/node_modules volumes, db data preserved) |

## Conventions

- **American English everywhere**. Use `""` for double quotes, `''` for single. **Never use em dashes** (use a period, comma, or parentheses instead).
- **Python**: src layout (`backend/src/my_family_tree/`). `ruff` for lint+format. `ty` for typecheck. No relative imports outside the package. Use `structlog` only (no `print`, no stdlib `logging` directly). Pydantic v2.
- **TypeScript**: `oxlint` for lint, `tsgo` (TS native-preview) for typecheck, `prettier` for format. `@/` alias for `src/`. TanStack Router file-based routes. TanStack Query for data fetching. `react-hook-form` + `zod` for forms.
- **Migrations**: hand-reviewed even when autogenerated. One logical change per migration. `pgvector` extension is created in the first migration before any model tables.
- **Secrets**: never in code, never in tests. Always via `Settings` (pydantic-settings).
- **Commits**: each commit is one sentence with no ending punctuation, prefixed with an appropriate emoji. Authored as `Ryan Lefkowitz <rlefkowitz1800@yahoo.com>`. **Never** add Claude as co-author.

## Where things live

- `backend/src/my_family_tree/models/` SQLModel tables (one file per aggregate)
- `backend/src/my_family_tree/mcp/tools/` MCP tool registry (single source backing the MCP server and the in-process `ToolHost`)
- `backend/src/my_family_tree/llm/` Provider abstraction (OpenAI, Anthropic) with provider-neutral dataclasses
- `backend/src/my_family_tree/ingest/` Per-kind extractors and pipeline orchestration
- `backend/src/my_family_tree/agent/` Chat loop, deep-research and conflict-resolver subagents
- `backend/src/my_family_tree/api/` FastAPI app, routers, middleware, deps
- `backend/src/my_family_tree/workers/` arq worker entrypoint and jobs
- `frontend/src/routes/` File-based pages
- `frontend/src/features/` Vertical slices (components + hooks + types per feature)
- `frontend/src/components/ui/` shadcn primitives (do not hand-edit)
- `infra/terraform/{modules,envs}/` Terraform modules and per-env compositions

## Gotchas

- `uv sync` must run from `backend/`. Same for `alembic`.
- After changing API endpoints: `make openapi && make gen-types` to refresh the frontend's typed client. CI verifies the diff is empty.
- First `pre-commit` run downloads `ty` and friends and is slow. Subsequent runs are fast.
- MCP behind ALB requires sticky sessions (Streamable HTTP holds session state). Already configured in Terraform; do not disable.
- `vector(3072)` cannot be HNSW-indexed (2000-dim cap). Always query `embedding_half halfvec(3072)`.
- `tree_id` column on every domain row even though we are single-user. Do not remove it; it makes the eventual multi-user transition trivial.
- The chat agent has no canonical-write tools. All writes go through `proposal` rows that the user (or an explicit auto-approve policy, off by default) applies via the `/proposals/{id}/approve` API endpoint. Do not try to add MCP tools that bypass this.
- When you edit `backend/src/my_family_tree/agent/system_prompt.py`, bump `CHAT_PROMPT_VERSION`. It is the inference cache key; without a bump, cached completions don't reflect prompt changes.
- `AsyncSession` is not concurrency-safe. Don't `asyncio.gather` two awaits that share the same session. Either await sequentially or open a second session.

## Don't

- Don't use LiteLLM, axios, React Router (use TanStack Router), ESLint or Biome (use oxlint), tsc for typecheck (use tsgo), Black (use ruff), mypy (use ty), poetry / pip-tools (use uv).
- Don't use em dashes anywhere.
- Don't add emoji to code or comments. Emoji is required in commit messages, forbidden in code.
- Don't credit Claude or Claude Code as commit author or co-author.
- Don't propose new MCP tools that mutate canonical entities directly. Always go through proposals.
- Don't put real PII (real family member names, birth dates, places, contact info) anywhere in the repo: source, tests, fixtures, seed data, docstrings, examples, docs, commit messages, or PR descriptions. Use neutral fictional examples like "Jane Doe", "April 15, 1932", "Boston, MA". `Ryan Lefkowitz <rlefkowitz1800@yahoo.com>` as commit / package author is the only allowed real-name reference.

## Skills

- `mft-bootstrap` Fresh-environment walkthrough.
- `mft-add-mcp-tool` Template for a new MCP tool with registration and integration test.
- `mft-add-route` Template for a new API endpoint with router, schema, service, test, and reminder to regen frontend types.
- `mft-new-migration` Autogenerate + hand-review prompts.
- `mft-add-shadcn` Add a shadcn primitive correctly.
