#!/usr/bin/env python3
"""
Full G8 re-ingest with split-subitem extraction rule.

Clears all tasks + OCR cache, enqueues theme-stream digitization.
Post-processing is skipped (skip_post_processing=true).

Usage:
    docker exec content-worker python /app/scripts/reingest_algebra8_split.py
    docker exec content-worker python /app/scripts/reingest_algebra8_split.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import uuid
from pathlib import Path

sys.path.insert(0, "/app")

import arq
from sqlalchemy import create_engine, text
from urllib.parse import urlparse

from src.core.config import get_settings
from src.core.job_state import JobStateManager

TEXTBOOK_ID = "e8f3a1b2-7c4d-5e6f-8091-2345678abcde"
PDF = "/textbooks/8_grade/www.idum.uz__algebra_8_rus.pdf"
CLASS_LEVEL = 8


def clear_db(engine) -> tuple[int, int]:
    with engine.begin() as conn:
        n_tm = conn.execute(
            text("""
                DELETE FROM tasks_master tm
                USING textbook_tasks tt
                WHERE tt.textbook_id = CAST(:tid AS UUID)
                  AND tt.task_id = tm.id
            """),
            {"tid": TEXTBOOK_ID},
        ).rowcount
        n_orphan = conn.execute(
            text("DELETE FROM tasks_master WHERE id LIKE 'G8_ALG_%'"),
        ).rowcount
        n_tt = conn.execute(
            text("DELETE FROM textbook_tasks WHERE textbook_id = CAST(:tid AS UUID)"),
            {"tid": TEXTBOOK_ID},
        ).rowcount
        conn.execute(
            text("""
                UPDATE textbooks
                SET digitization_status = 'pending',
                    digitization_progress = 0,
                    tasks_extracted = 0,
                    tasks_skipped = 0
                WHERE textbook_id = CAST(:tid AS UUID)
            """),
            {"tid": TEXTBOOK_ID},
        )
    return n_tt, n_tm + n_orphan


def clear_ocr_cache() -> int:
    settings = get_settings()
    h = hashlib.sha256(Path(PDF).read_bytes()).hexdigest()[:16]
    cache_dir = Path(settings.pipeline_cache_dir)
    removed = 0
    for f in cache_dir.glob(f"gemini_{h}*.md"):
        f.unlink()
        removed += 1
    fig_dir = cache_dir / "figures" / TEXTBOOK_ID
    if fig_dir.exists():
        for f in fig_dir.glob("*.json"):
            f.unlink()
            removed += 1
    return removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        before = conn.execute(
            text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc tt ON tt.id = tm.toc_id
                WHERE tt.textbook_id = CAST(:tid AS UUID)
            """),
            {"tid": TEXTBOOK_ID},
        ).scalar()

    print(f"G8 re-ingest (split subitems): {before} tasks in DB now")

    if args.dry_run:
        print("[DRY-RUN] would clear DB + OCR cache + enqueue job")
        return 0

    n_tt, n_tm = clear_db(engine)
    n_cache = clear_ocr_cache()
    print(f"Cleared: textbook_tasks={n_tt}, tasks_master={n_tm}, cache_files={n_cache}")

    job_id = str(uuid.uuid4())
    JobStateManager().create(
        job_id=job_id,
        textbook_id=TEXTBOOK_ID,
        class_level=CLASS_LEVEL,
        source_type="pdf",
        source_path=PDF,
    )

    u = urlparse(get_settings().redis_url)

    async def go() -> None:
        pool = await arq.create_pool(
            arq.connections.RedisSettings(
                host=u.hostname or "localhost",
                port=u.port or 6379,
                database=int((u.path or "/0").lstrip("/") or "0"),
            )
        )
        try:
            await pool.enqueue_job("run_digitization_job", job_id)
        finally:
            await pool.aclose()

    asyncio.run(go())
    print(f"job_id = {job_id}")
    print(f"watch: docker logs -f content-worker 2>&1 | grep {job_id[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
