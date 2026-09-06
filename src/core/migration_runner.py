"""Run Alembic once per database, even when the API has several replicas.

content-service used to apply no migrations at all: its entrypoint only fixed
volume ownership and exec'd uvicorn. The schema was therefore advanced by hand
on the deployed databases, drifted away from the revision Alembic had recorded,
and eventually lost columns the task query depends on — every
``GET /api/v1/content/tasks`` answered 500, taking exam generation and
diagnostic sessions down with it. Startup now converges the schema, the same
way diagnostics-service does.
"""
from __future__ import annotations

import logging
import subprocess

from sqlalchemy import create_engine, text

from src.core.config import get_settings


log = logging.getLogger(__name__)
# Distinct from every other service's key: the lock is per database, but an
# accidental collision across services would serialise unrelated deploys.
_MIGRATION_LOCK_KEY = 814_042_073


def main() -> None:
    """Serialise schema upgrades with a PostgreSQL advisory lock.

    Uvicorn workers and horizontally scaled containers must never race while
    creating an index or adding a column. The lock connection stays open until
    the child Alembic process has finished its transaction.
    """
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _MIGRATION_LOCK_KEY})
        try:
            result = subprocess.run(
                ["alembic", "upgrade", "head"],
                capture_output=True,
                text=True,
                check=True,
            )
            if result.stdout:
                log.info("Alembic migrations applied:\n%s", result.stdout)
        except subprocess.CalledProcessError as exc:
            log.error("Alembic migration failed:\n%s\n%s", exc.stdout, exc.stderr)
            raise
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _MIGRATION_LOCK_KEY})
            connection.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
