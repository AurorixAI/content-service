# ── Stage 1: dependencies ────────────────────────────────────────────────────
FROM python:3.12-slim AS deps

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# System libs for psycopg2 + curl for the Docker healthcheck.
# nodejs — для KaTeX-гейта (src/validate/katex.py вызывает katex_compile.js).
# Без него компиляция формул «мягко пропускается»: гейт не падает, но и не
# работает — проверено фактом на первом живом прогоне, где `compile_measured`
# был False у всей книги, а в логе стояло «не найден `node` в PATH».
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    gosu \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
# KaTeX ставится из package.json — версия закреплена там (katex@0.16.11).
COPY package.json package-lock.json ./
RUN npm install --omit=dev --no-audit --no-fund

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
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8004"]
