# Contributing

## Local setup

```bash
git clone <repo> && cd my-family-tree
cp .env.example .env       # add OPENAI_API_KEY / ANTHROPIC_API_KEY
make bootstrap             # tool checks + uv sync + yarn install + pre-commit install
make up                    # docker compose up
make migrate && make seed
```

Then `http://localhost:5173` (frontend) and `http://localhost:8000/healthz`
(api).

## Branch + PR conventions

- Branch name: `<author>/<kebab-case-title>` (e.g. `ryan/fix-place-merge`).
- One logical change per PR. Splittable PRs are better than monoliths.
- PR title: Title Case, no trailing punctuation.
- PR body uses the [pull_request_template](../.github/pull_request_template.md).

## Commit conventions

- One sentence per commit, no ending punctuation.
- Prefixed with an appropriate emoji (🌱 scaffold, 🐳 docker, 📦 package,
  🧬 schema, 🛠️ tool, 🚀 api, 🧪 test, 🎨 frontend, 🪝 hooks, 🤝 ci, 🏗️ infra,
  📖 docs, 🪪 claude).
- Authored as `Ryan Lefkowitz <rlefkowitz1800@yahoo.com>` (use `--author` if
  your local `git config user.email` differs).
- **Never** add Claude or Claude Code as co-author.

## Style

- American English. Use `""` for double quotes, `''` for single. **No em dashes.**
- Python: src layout, ruff for lint+format, ty for typecheck, structlog only.
- TypeScript: ESLint flat config + Prettier, `@/` alias, TanStack Router file-based.
- One logical change per migration; hand-review autogenerate output.

## Common tasks

- Add an MCP tool: see `mcp/tools/persons.py` as a template.
- Add an API endpoint: add a router under `api/routers/` and register it in
  `api/app.py`. Then `make openapi && make gen-types`.
- Add a SQLModel: add it under `models/`, register in `models/__init__.py`,
  generate a migration with `make migration M="add foo"`, hand-review.
- Add a shadcn primitive: `cd frontend && npx shadcn@latest add <name>`.
