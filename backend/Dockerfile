# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.14
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libtesseract-dev \
        libpq5 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

# Cache deps before copying source so changing source does not invalidate the
# dependency layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY alembic.ini ./
COPY README.md* ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM base AS runtime

LABEL org.opencontainers.image.title="my-family-tree-backend" \
      org.opencontainers.image.description="My Family Tree backend (api, worker, mcp)" \
      org.opencontainers.image.licenses="MIT"

RUN groupadd --system app \
 && useradd --system --gid app --home-dir /app --shell /bin/bash app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src"

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "my_family_tree.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
