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

## v1.5 (Persist Chat Records PR)

- [x] Wire `ChatAgent` + `ToolHost` into the chat endpoint so the LLM has the
      full MCP tool surface
- [x] SSE streaming chat (`POST /api/v1/chat/stream`) with live deltas + tool
      cards
- [x] Full propose-write tool surface: person update/merge, relationship
      create/delete, event create/update, place create, source create,
      claim accept/reject, request_user_input
- [x] Proposal applier with per-(action, target_type) dispatch
- [x] User-assertion `Source` + per-fact `Claim` + `FactProvenance` written
      automatically on approve
- [x] `POST /proposals/approve_batch` with dependency-ordered savepoints
- [x] Frontend `/proposals` page with diff view, individual + bulk approve,
      `/proposals?ids=...` deep-link from chat bubbles
- [x] One-shot `migrate` compose service so `make up` always lands on a
      migrated schema
- [x] Updated system prompt teaching the agent the propose-first pattern

## v2 (deferred to follow-ups)

- Conflict-resolution side-by-side UI with "ask agent" button
- Interactive tree visualization (react-flow + dagre, confidence-coded edges)
- Bulk-resolve wizard for first GEDCOM import (currently floods conflicts)
- Vision-LLM OCR fallback at the page level (currently doc-level)
- Cross-encoder rerank on hybrid search results
- GEDCOM 7 export
- Authentication (single-user with shared password, then multi-user)
- [x] External research tools (web + genealogy MCP tools, optional providers)
- Deep research orchestration with planning
- Async resume for `request_user_input` (queue + paired reply)
- Argument-token streaming on tool calls (currently we stream final input)
- Synchronous post-apply conflict-rule sweep (currently nightly only)
- ECS task autoscaling (currently fixed desired_count)
- CloudFront in front of the frontend bucket
