# Roadmap

## v1 (this PR)

- [x] Backend scaffold (Python 3.14, FastAPI, SQLModel, Alembic, pgvector)
- [x] Data model (20 tables) + initial migration with extensions, indexes
- [x] Storage adapter (MinIO + S3, path-style aware)
- [x] LLM provider abstraction (OpenAI Responses + Anthropic Messages, no LiteLLM)
- [x] MCP server (stdio + Streamable HTTP) with shared registry
- [x] Read tools: persons, documents, conflicts, chunks, stats
- [x] Propose-write tools backed by `proposal` table
- [x] Ingestion pipeline (pdf, image, text, gedcom, note) with arq workers
- [x] Embeddings runner + hybrid retrieval (RRF over vector + FTS)
- [x] Person dedup (blocking + scoring) and merge mechanics
- [x] Conflict detection rules with stable IDs
- [x] Chat agent loop with streaming tool execution
- [x] Frontend (Vite + React + TS + Tailwind v4 + shadcn + TanStack Router/Query)
- [x] Pages: dashboard, people, documents, conflicts, chat, tree (placeholder)
- [x] Backend unit tests (dates, ids, chunking, dedup, conflicts, registry)
- [x] docker-compose stack (db, redis, minio, api, worker, mcp, frontend)
- [x] Pre-commit hooks (ruff, ty, prettier, eslint, gitleaks, emoji-commit)
- [x] GitHub Actions CI + soft no-direct-push guardrail
- [x] Terraform: bootstrap + modules (network, alb, ecs, rds, s3, secrets, iam) + dev/prod envs

## v2 (deferred to follow-ups)

- Streaming chat UI with tool-call timeline rendering
- Conflict-resolution side-by-side UI with "ask agent" button
- Interactive tree visualization (react-flow + dagre, confidence-coded edges)
- Bulk-resolve wizard for first GEDCOM import (currently floods conflicts)
- Vision-LLM OCR fallback at the page level (currently doc-level)
- Cross-encoder rerank on hybrid search results
- GEDCOM 7 export
- Authentication (single-user with shared password, then multi-user)
- Deep research subagent with full plan/search/extract/propose loop
- Bulk auto-approve UI gesture for trusted batches
- ECS task autoscaling (currently fixed desired_count)
- CloudFront in front of the frontend bucket
