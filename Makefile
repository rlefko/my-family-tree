SHELL := /bin/bash
.PHONY: help bootstrap up down nuke logs ps shell-api shell-db migrate migration seed \
  test test-backend test-frontend test-int lint format typecheck openapi gen-types \
  mcp-stdio mcp-http tf-fmt tf-validate tf-plan-dev clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Tool checks, uv sync, yarn install, pre-commit install
	@command -v docker >/dev/null || (echo "docker not found" && exit 1)
	@command -v uv >/dev/null || (echo "install uv: https://docs.astral.sh/uv/getting-started/installation/" && exit 1)
	@command -v yarn >/dev/null || (echo "install yarn: npm i -g yarn" && exit 1)
	@command -v node >/dev/null || (echo "install node 20+" && exit 1)
	@test -f .env || cp .env.example .env
	cd backend && uv sync --all-groups
	cd frontend && yarn install --frozen-lockfile
	@command -v pre-commit >/dev/null && pre-commit install || echo "pre-commit not installed; skipping hook install"

up: ## Start the full stack via docker-compose
	docker compose up -d

down: ## Stop the stack
	docker compose down

nuke: ## Stop and remove volumes (data loss)
	docker compose down -v

logs: ## Tail all logs
	docker compose logs -f

ps: ## List running services
	docker compose ps

shell-api: ## Bash shell in the api container
	docker compose exec api bash

shell-db: ## psql shell in the db container
	docker compose exec db psql -U $${POSTGRES_USER:-my_family_tree} -d $${POSTGRES_DB:-my_family_tree}

migrate: ## Apply Alembic migrations to head
	docker compose exec api alembic upgrade head

migration: ## Autogenerate a migration: make migration M="add foo"
	@test -n "$(M)" || (echo "Usage: make migration M=\"description\"" && exit 1)
	docker compose exec api alembic revision --autogenerate -m "$(M)"

seed: ## Load demo seed data
	docker compose exec api python -m my_family_tree seed || echo "seed command not yet implemented"

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend unit tests (no containers)
	cd backend && uv run pytest -m "unit" -q

test-frontend: ## Run frontend tests
	cd frontend && yarn test

test-int: ## Run backend integration tests (requires testcontainers + docker)
	cd backend && uv run pytest -m "integration" -q

lint: ## Lint backend + frontend
	cd backend && uv run ruff check
	cd frontend && yarn lint

format: ## Format backend + frontend
	cd backend && uv run ruff format
	cd frontend && yarn format

typecheck: ## Typecheck backend + frontend
	cd backend && uv run ty check src tests
	cd frontend && yarn typecheck

openapi: ## Dump OpenAPI JSON to backend/openapi.json (requires running api)
	curl -fsS http://localhost:8000/openapi.json > backend/openapi.json
	@echo "wrote backend/openapi.json"

gen-types: ## Regenerate frontend typed client from openapi.json
	cd frontend && yarn gen:types

mcp-stdio: ## Run MCP server in stdio mode (for Claude Desktop)
	cd backend && uv run python -m my_family_tree.cli mcp --transport stdio

mcp-http: ## Show health of mcp HTTP service
	curl -fsS http://localhost:8765/healthz || echo "mcp not reachable"

tf-fmt: ## Format Terraform files
	terraform -chdir=infra/terraform fmt -recursive

tf-validate: ## Validate every Terraform env
	@for env in infra/terraform/envs/*; do \
	  echo "validating $$env"; \
	  (cd $$env && terraform init -backend=false -input=false >/dev/null && terraform validate); \
	done

tf-plan-dev: ## terraform plan against dev env (requires AWS credentials)
	cd infra/terraform/envs/dev && terraform init -input=false && terraform plan

clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/.ty_cache backend/htmlcov backend/dist
	rm -rf frontend/dist frontend/coverage
