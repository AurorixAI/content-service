# ── Stage 1: dependencies ────────────────────────────────────────────────────
FROM python:3.12-slim AS deps

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Test tooling ────────────────────────────────────────────────────────────
# Kept separate from the production runtime.  The offline LaTeX audit invokes
# KaTeX through Node, so a CI-equivalent test target needs both Python and
# Node.  Production requests never load this stage.
FROM deps AS test

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pytest

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY pytest.ini .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# System libs for psycopg2 + curl for the Docker healthcheck + nodejs for KaTeX validation
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    gosu \
    curl \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY --from=test /app/node_modules /app/node_modules
COPY src/ ./src/
COPY data/ ./data/
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/
COPY alembic.ini .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Pipeline cache directory
RUN mkdir -p /app/data/pipeline_cache

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Non-root user (entrypoint will chown volumes then exec as this user)
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN chown -R appuser:appgroup /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8004

ENTRYPOINT ["docker-entrypoint.sh"]
# Migrations run to completion before the first worker starts, so a request
# can never reach a half-upgraded schema.
CMD ["sh", "-c", "python -m src.core.migration_runner && exec uvicorn src.main:app --host 0.0.0.0 --port 8004"]
