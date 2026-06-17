#!/usr/bin/env python3
"""Re-enqueue digitization for an existing textbook (after TOC fix).

Usage:
    docker exec content-worker python /app/scripts/restart_digitization.py \\
        --textbook-id 69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f \\
        --class 7 \\
        --pdf /textbooks/7_grade/1701411287_algebra_-uchebnik_-7-kl_-makarychev_compressed.pdf
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

import arq
from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.core.job_state import JobStateManager


def _arq_redis_settings():
    from urllib.parse import urlparse
    s = get_settings()
    u = urlparse(s.redis_url)
    return arq.connections.RedisSettings(
        host=u.hostname or "localhost",
        port=u.port or 6379,
        database=int((u.path or "/0").lstrip("/") or "0"),
    )


async def _enqueue(job_id: str) -> None:
    pool = await arq.create_pool(_arq_redis_settings())
    try:
        await pool.enqueue_job("run_digitization_job", job_id)
    finally:
        await pool.aclose()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--textbook-id", required=True)
    ap.add_argument("--class", dest="class_level", type=int, required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--clear-tasks", action="store_true",
                    help="Delete existing tasks for this textbook")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    if args.clear_tasks:
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM tasks_master tm
                USING textbook_tasks tt
                WHERE tt.textbook_id = CAST(:tid AS UUID)
                  AND tt.task_id = tm.id
            """), {"tid": args.textbook_id})
            conn.execute(text("""
                DELETE FROM textbook_tasks WHERE textbook_id = CAST(:tid AS UUID)
            """), {"tid": args.textbook_id})
            print("[OK] Cleared textbook tasks")

    job_id = str(uuid.uuid4())
    JobStateManager().create(
        job_id=job_id,
        textbook_id=args.textbook_id,
        class_level=args.class_level,
        source_type="pdf",
        source_path=args.pdf,
    )
    asyncio.run(_enqueue(job_id))
    print(f"job_id = {job_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
