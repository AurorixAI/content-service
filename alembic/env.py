"""
Alembic env.py — ALGO Content Service

Content-service uses SQLAlchemy Core (raw SQL, no ORM models),
so target_metadata = None and migrations are written by hand.

DATABASE_URL is read from the DATABASE_URL environment variable.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Alembic Config object (gives access to alembic.ini values) ────────────
config = context.config

# ── Logging ──────────────────────────────────────────────────────────────
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── No ORM models — raw SQL migrations only ───────────────────────────────
target_metadata = None

# ── Database URL: env var wins, then alembic.ini ──────────────────────────
def get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Export it before running alembic commands."
        )
    return url


# ── Offline mode (no live DB connection needed; generates SQL script) ──────
def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (runs against a live DB) ──────────────────────────────────
def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
