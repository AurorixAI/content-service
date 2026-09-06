#!/usr/bin/env python3
"""Starts digitization job for Alimov Grade 9 textbook."""
from __future__ import annotations
import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

from src.core.job_state import JobStateManager
from src.core.config import get_settings

TEXTBOOK_ID = "2aa7af81-af13-42f9-a26b-e7e6bebaa4e6"
PDF_PATH = "/app/textbooks/9_grade/www.idum.uz__algebra_9_rus.pdf"

async def _enqueue_job(job_id: str) -> None:
    import redis.asyncio as aioredis
    settings = get_settings()
    
    # Extract redis parameters from URL
    redis_url = settings.redis_url
    log_info = f"Connecting to Redis at {redis_url}"
    print(log_info)
    
    # We enqueue to default arq queue
    conn = await aioredis.from_url(redis_url)
    # The job info is put into the arq queue
    job_data = {
        "job_id": job_id,
        "textbook_id": TEXTBOOK_ID,
        "source_path": PDF_PATH
    }
    
    # Enqueue a task for the worker
    # We call the 'digitize_textbook' arq task
    from arq import create_pool
    from arq.connections import RedisSettings
    
    # Parse redis url manually to match RedisSettings
    # e.g., redis://redis:6379/0
    import urllib.parse
    parsed = urllib.parse.urlparse(redis_url)
    host = parsed.hostname or "redis"
    port = parsed.port or 6379
    db = int(parsed.path.lstrip("/")) if parsed.path else 0
    
    redis_settings = RedisSettings(host=host, port=port, database=db)
    pool = await create_pool(redis_settings)
    await pool.enqueue_job("run_digitization_job", job_id)
    print(f"Enqueued job {job_id} on arq queue successfully.")

def main():
    job_id = str(uuid.uuid4())
    state = JobStateManager()
    state.create(
        job_id=job_id,
        textbook_id=TEXTBOOK_ID,
        class_level=9,
        source_type="pdf",
        source_path=PDF_PATH,
    )
    print(f"Created job state in DB. Job ID: {job_id}")
    asyncio.run(_enqueue_job(job_id))
    print(f"Digitization job started. You can track progress in the UI or logs.")

if __name__ == "__main__":
    main()
