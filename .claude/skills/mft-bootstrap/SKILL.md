---
name: mft-bootstrap
description: Walk a new contributor (or a fresh dev environment) through getting My Family Tree running locally end-to-end.
---

Use when the user asks to set up or refresh the local environment.

Steps to run, in order:

1. Verify required tools: `docker`, `uv`, `yarn`, `node` (>=20), and (optional) `pre-commit`.
2. `cp .env.example .env` if `.env` doesn't exist; ask the user to fill in
   `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`.
3. `make bootstrap` (uv sync + yarn install + pre-commit install).
4. `make up` to bring up the docker-compose stack.
5. Wait for healthchecks, then `make migrate && make seed`.
6. Verify:
   - `curl http://localhost:8000/healthz` -> 200 with `db: ok`, `s3: ok`.
   - `http://localhost:5173/` renders the dashboard.
7. If anything fails, run `make logs` and surface the failing service.

Don't skip `make migrate`; the schema doesn't exist until it runs.
