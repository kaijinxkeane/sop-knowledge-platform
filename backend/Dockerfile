# Build context: repository root (needs backend/ and scripts/llm-wiki).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# LibreOffice Impress (headless) renders slide pictures; fonts so slides look right.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libreoffice-impress-nogui \
       fonts-dejavu-core fonts-liberation2 fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev
# One copy of the llm-wiki helpers, loaded by wiki_core.
COPY scripts/llm-wiki /app/vendor/llm-wiki

RUN useradd --system --uid 10001 --home /app sop && mkdir -p /cache && chown -R sop /app /cache
USER sop

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli sync-config && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log"]
