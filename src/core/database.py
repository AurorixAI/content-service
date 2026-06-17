"""Content Service — shared database connection pool for API endpoints."""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from src.core.config import get_settings

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = create_engine(
            s.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_db() -> Generator[Connection, None, None]:
    """FastAPI dependency — yields a read-only SQLAlchemy connection."""
    with _get_engine().connect() as conn:
        yield conn
