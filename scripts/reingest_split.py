#!/usr/bin/env python3
"""
Re-ingest one or more textbooks with the split-subitem extraction rule.

Usage (run after G8 finishes):
    # G6 School (theme_stream, worst: 592 compound):
    docker exec content-worker python /app/scripts/reingest_split.py --key g6_local

    # G7 School (per-paragraph, 370 compound):
    docker exec content-worker python /app/scripts/reingest_split.py --key g7_algebra

    # All affected books (queue sequentially — worker handles one at a time):
    docker exec content-worker python /app/scripts/reingest_split.py --key g6_local g7_algebra g6_vilenkin g7_makarychev

    # Dry run:
    docker exec content-worker python /app/scripts/reingest_split.py --key g6_local --dry-run
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

BOOKS = {
    "g6_local": {
        "id": "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8",
        "class_level": 6,
        "title": "Математика 6 класс — Школьное издание",
        "pdf": "/textbooks/6_grade/6 класс математика школа.pdf",
        "prefix": "G6_TB",
    },
    "g7_algebra": {
        "id": "4b19752a-3d54-4538-b6a6-26ce1fbb48fd",
        "class_level": 7,
        "title": "Алгебра 7 класс — Школьное издание",
        "pdf": "/textbooks/7_grade/Алгебра 7 класс.pdf",
        "prefix": "G7_ALG",
    },
    "g6_vilenkin": {
        "id": "351a95c1-5208-4ae9-8323-6d7dd5e8bb82",
        "class_level": 6,
        "title": "Математика 6 класс — Виленкин",
        "pdf": "/textbooks/6_grade/Виленкин 6 класс.pdf",
        "prefix": "G6_TB",
    },
    "g7_makarychev": {
        "id": "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f",
        "class_level": 7,
        "title": "Алгебра 7 класс — Макарычев",
        "pdf": "/textbooks/7_grade/1701411287_algebra_-uchebnik_-7-kl_-makarychev_compressed.pdf",
        "prefix": "G7_TB",
    },
    "g5_vilenkin": {
        "id": "184640af-64e7-47af-a974-8b8112e6ffb2",
        "class_level": 5,
        "title": "Математика 5 класс — Виленкин",
        "pdf": "/textbooks/5_grade/vklasse_matematuka_5_klass_vilenkin_johov_chesnokov_shvarcbyrd_2013.pdf",
        "prefix": "G5_TB",
    },
}


def compound_count(engine, tid: str) -> tuple[int, int]:
    with engine.connect() as conn:
        total = conn.execute(
            text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc tt ON tt.id = tm.toc_id
                WHERE tt.textbook_id = CAST(:tid AS UUID)
            """),
            {"tid": tid},
        ).scalar()
        compound = conn.execute(
            text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc tt ON tt.id = tm.toc_id
                WHERE tt.textbook_id = CAST(:tid AS UUID)
                  AND tm.question_text LIKE '%1)%'
                  AND tm.question_text LIKE '%2)%'
            """),
            {"tid": tid},
        ).scalar()
    return total, compound


def clear_and_queue(engine, book: dict, dry_run: bool) -> str | None:
    tid = book["id"]
    pdf = book["pdf"]
    prefix = book["prefix"]

    total, compound = compound_count(engine, tid)
    print(f"\n  {book['title']}")
    print(f"  Tasks in DB: {total} total, {compound} likely compound")

    if dry_run:
        print("  [DRY-RUN] skipped")
        return None

    # Count OCR cache (keep it — re-extraction reuses cached text, no re-OCR needed)
    h = hashlib.sha256(Path(pdf).read_bytes()).hexdigest()[:16]
    cache_dir = Path(get_settings().pipeline_cache_dir)
    n_cache = len(list(cache_dir.glob(f"gemini_{h}*.md")))
    print(f"  OCR cache kept: {n_cache} pages on disk (extraction will reuse)")

    # Clear tasks
    with engine.begin() as conn:
        conn.execute(
            text("""
                DELETE FROM tasks_master tm
                USING textbook_tasks tt
                WHERE tt.textbook_id = CAST(:tid AS UUID)
                  AND tt.task_id = tm.id
            """),
            {"tid": tid},
        )
        conn.execute(
            text("DELETE FROM textbook_tasks WHERE textbook_id = CAST(:tid AS UUID)"),
            {"tid": tid},
        )
        conn.execute(
            text(f"DELETE FROM tasks_master WHERE id LIKE '{prefix}_%'"),
        )
        conn.execute(
            text("""
                UPDATE textbooks
                SET digitization_status = 'pending',
                    digitization_progress = 0,
                    tasks_extracted = 0,
                    tasks_skipped = 0
                WHERE textbook_id = CAST(:tid AS UUID)
            """),
            {"tid": tid},
        )
    print(f"  DB cleared")

    job_id = str(uuid.uuid4())
    JobStateManager().create(
        job_id=job_id,
        textbook_id=tid,
        class_level=book["class_level"],
        source_type="pdf",
        source_path=pdf,
    )
    return job_id


async def _enqueue_all(job_ids: list[str]) -> None:
    s = get_settings()
    u = urlparse(s.redis_url)
    pool = await arq.create_pool(
        arq.connections.RedisSettings(
            host=u.hostname or "localhost",
            port=u.port or 6379,
            database=int((u.path or "/0").lstrip("/") or "0"),
        )
    )
    try:
        for jid in job_ids:
            await pool.enqueue_job("run_digitization_job", jid)
            print(f"  queued job: {jid}")
    finally:
        await pool.aclose()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", nargs="+",
                    choices=list(BOOKS.keys()),
                    required=True,
                    help="Book key(s) to re-ingest")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    job_ids = []

    print(f"Re-ingest with split-subitem rule: {args.key}")
    for key in args.key:
        jid = clear_and_queue(engine, BOOKS[key], args.dry_run)
        if jid:
            job_ids.append(jid)

    if job_ids:
        asyncio.run(_enqueue_all(job_ids))
        print(f"\nQueued {len(job_ids)} job(s). Worker handles one at a time.")
        print("Monitor: docker logs -f content-worker 2>&1")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
