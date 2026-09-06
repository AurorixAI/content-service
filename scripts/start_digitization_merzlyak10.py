#!/usr/bin/env python3
"""Запуск оцифровки — Алгебра 10 класс (Мерзляк, базовый уровень)."""
from __future__ import annotations
import asyncio
import sys
import uuid
import urllib.parse

sys.path.insert(0, "/app")

from src.core.job_state import JobStateManager
from src.core.config import get_settings

TEXTBOOK_ID = "e92457e0-c22d-4485-b838-6962ecd7413f"
PDF_PATH = "/app/textbooks/10_grade/1636978873_algebra-10-kl_-baz_ur_-merzljak.pdf"
CLASS_LEVEL = 10


async def _enqueue_job(job_id: str) -> None:
    from arq import create_pool
    from arq.connections import RedisSettings

    settings = get_settings()
    redis_url = settings.redis_url
    print(f"Connecting to Redis at {redis_url}")

    parsed = urllib.parse.urlparse(redis_url)
    host = parsed.hostname or "redis"
    port = parsed.port or 6379
    db = int(parsed.path.lstrip("/")) if parsed.path else 0

    redis_settings = RedisSettings(host=host, port=port, database=db)
    pool = await create_pool(redis_settings)
    await pool.enqueue_job("run_digitization_job", job_id)
    print(f"✅ Enqueued job {job_id} on arq queue successfully.")


def main():
    job_id = str(uuid.uuid4())
    state = JobStateManager()
    state.create(
        job_id=job_id,
        textbook_id=TEXTBOOK_ID,
        class_level=CLASS_LEVEL,
        source_type="pdf",
        source_path=PDF_PATH,
    )
    print(f"📚 Textbook : Алгебра 10 класс (Мерзляк, базовый)")
    print(f"🆔 Job ID   : {job_id}")
    print(f"📄 PDF      : {PDF_PATH}")
    asyncio.run(_enqueue_job(job_id))
    print(f"🚀 Digitization started! Track progress in logs.")


if __name__ == "__main__":
    main()
