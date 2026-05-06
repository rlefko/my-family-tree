# My Family Tree

A personal genealogy research workbench. Upload family documents (PDFs, images, plain text, GEDCOM, free-form notes), let an AI agent extract evidence, build the tree, surface conflicts for you to resolve, and run "deep research" to find new records. The agent reads freely and writes only as proposals you approve.

## Quick start

```bash
git clone <repo> && cd my-family-tree
cp .env.example .env       # add OPENAI_API_KEY and/or ANTHROPIC_API_KEY
make bootstrap             # tool checks, uv sync, yarn install, pre-commit install
make up                    # docker compose up for db, redis, minio, api, worker, mcp, frontend
make migrate && make seed  # apply schema, load demo data
```

Then open `http://localhost:5173`.

## Stack

| Area | Choice |
|------|--------|
| Backend | Python 3.14, FastAPI, SQLAlchemy 2 + SQLModel, Alembic, Pydantic, arq |
| Database | Postgres 17 + `pgvector` (HNSW on `halfvec(3072)`), `pg_trgm`, GIN-FTS |
| Object storage | MinIO locally, S3 in prod |
| LLMs | OpenAI (`gpt-5.5`, default) and Anthropic (Claude Opus 4.7 / Sonnet 4.6); direct SDKs, no abstraction layer |
| Embeddings | OpenAI `text-embedding-3-large` (3072 dims) |
| MCP | Official `mcp` Python SDK, stdio + Streamable HTTP transports |
| Frontend | TypeScript, React 18, Vite, Tailwind v4, shadcn/ui, TanStack Router + Query |
| Infra | Terraform on AWS (VPC, ECS Fargate, RDS, S3, ALB, Secrets Manager) |
| CI | GitHub Actions |
| Tooling | `uv`, `yarn`, `ruff`, `ty`, `pytest`, `vitest`, `oxlint`, `tsgo`, `prettier`, `pre-commit` |

## Layout

```
backend/      FastAPI app, MCP server, arq workers, ingestion, agent loop
frontend/     Vite + React UI
infra/        Terraform modules and per-env compositions
docs/         Architecture, data model, ingestion, agent, MCP, deployment
scripts/      Shell helpers used by Make and CI
.github/      CI workflows, CODEOWNERS, PR template
.claude/      Claude Code skills and settings
```

## Docs

- [Architecture overview](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Ingestion pipeline](docs/ingestion.md)
- [Agent and MCP](docs/agent.md)
- [MCP server](docs/mcp.md)
- [Conflict detection](docs/conflicts.md)
- [Deployment](docs/deployment.md)
- [Contributing](docs/contributing.md)
- [Roadmap](docs/roadmap.md)

## License

MIT. See [LICENSE](LICENSE).
