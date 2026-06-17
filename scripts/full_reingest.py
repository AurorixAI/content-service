#!/usr/bin/env python3
"""Full re-ingest textbooks with upgraded pipeline (max quality).

Clears tasks + OCR cache, enqueues digitization job(s) directly in ARQ.
Run one book at a time — pass a single key unless you intentionally want several queued.

Usage:
    # All textbooks (recommended):
    docker exec content-worker python /app/scripts/full_reingest.py --all

    # Specific keys:
    docker exec content-worker python /app/scripts/full_reingest.py --keys g5_idum_ch1,g6_local,g7_makarychev

    # By grade (one book per grade — legacy):
    docker exec content-worker python /app/scripts/full_reingest.py --grades 5,6,7

    # Dry-run:
    docker exec content-worker python /app/scripts/full_reingest.py --all --dry-run
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

from src.core.config import get_settings
from src.core.job_state import JobStateManager
from src.core.job_enqueue import clear_arq_digitization_queue, enqueue_digitization

# Books with complete exercise-range tables — digitize next
READY_KEYS: list[str] = [
    "g6_local",
    "g7_makarychev",
]

# Done — never re-queue or re-ingest (digitization complete)
FINISHED_KEYS = {"g5_vilenkin", "g5_idum_ch1", "g5_idum_ch2"}

# Defer until exercise-range tables are filled (OCR gaps / no TOC)
DEFER_KEYS = {"g6_vilenkin", "g7_algebra", "g5_vilenkin_dup", *FINISHED_KEYS}

# Ordered queue — max quality for every active textbook with PDF
ALL_TEXTBOOKS: list[dict] = [
    {
        "key": "g5_vilenkin",
        "id": "184640af-64e7-47af-a974-8b8112e6ffb2",
        "class_level": 5,
        "title": "Математика 5 класс — Виленкин",
        "pdf": "/textbooks/5_grade/vklasse_matematuka_5_klass_vilenkin_johov_chesnokov_shvarcbyrd_2013.pdf",
    },
    {
        "key": "g5_idum_ch1",
        "id": "5630a994-061d-4c20-9863-fe049c8059fb",
        "class_level": 5,
        "title": "Математика 5 класс — IDUM, часть 1",
        "pdf": "/textbooks/5_grade/matematika_1qism_5_rus.pdf",
    },
    {
        "key": "g5_idum_ch2",
        "id": "47167115-5961-4405-bb55-1bda8ce1b687",
        "class_level": 5,
        "title": "Математика 5 класс — IDUM, часть 2",
        "pdf": "/textbooks/5_grade/matematika_5_rus_2_chast_2020_www.idum.uz.pdf",
    },
    {
        "key": "g6_vilenkin",
        "id": "351a95c1-5208-4ae9-8323-6d7dd5e8bb82",
        "class_level": 6,
        "title": "Математика 6 класс — Виленкин",
        "pdf": "/textbooks/6_grade/Виленкин 6 класс.pdf",
    },
    {
        "key": "g6_local",
        "id": "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8",
        "class_level": 6,
        "title": "Математика 6 класс — Школьное издание",
        "pdf": "/textbooks/6_grade/6 класс математика школа.pdf",
    },
    {
        "key": "g7_makarychev",
        "id": "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f",
        "class_level": 7,
        "title": "Алгебра 7 класс — Макарычев",
        "pdf": "/textbooks/7_grade/1701411287_algebra_-uchebnik_-7-kl_-makarychev_compressed.pdf",
    },
    {
        "key": "g7_algebra",
        "id": "4b19752a-3d54-4538-b6a6-26ce1fbb48fd",
        "class_level": 7,
        "title": "Алгебра 7 класс — Школьное издание",
        "pdf": "/textbooks/7_grade/Алгебра 7 класс.pdf",
    },
    {
        "key": "g8_algebra",
        "id": "e8f3a1b2-7c4d-5e6f-8091-2345678abcde",
        "class_level": 8,
        "title": "Алгебра 8 класс — Школьное издание",
        "pdf": "/textbooks/8_grade/www.idum.uz__algebra_8_rus.pdf",
    },
]

# Default skip set (--all skips deferred + duplicate / no TOC)
SKIP_KEYS = DEFER_KEYS


def _by_key(key: str) -> dict | None:
    for tb in ALL_TEXTBOOKS:
        if tb["key"] == key:
            return tb
    return None


def _pdf_hash(pdf_path: str) -> str:
    return hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:16]


def clear_textbook(conn, textbook_id: str) -> int:
    r = conn.execute(
        text("""
            DELETE FROM tasks_master tm
            USING textbook_tasks tt
            WHERE tt.textbook_id = CAST(:tid AS UUID)
              AND tt.task_id = tm.id
        """),
        {"tid": textbook_id},
    )
    conn.execute(
        text("DELETE FROM textbook_tasks WHERE textbook_id = CAST(:tid AS UUID)"),
        {"tid": textbook_id},
    )
    conn.execute(
        text("""
            UPDATE textbooks
            SET digitization_status = 'pending',
                digitization_progress = 0,
                tasks_extracted = 0,
                tasks_skipped = 0,
                figures_skipped = 0
            WHERE textbook_id = CAST(:tid AS UUID)
        """),
        {"tid": textbook_id},
    )
    return r.rowcount


def clear_ocr_cache(pdf_path: str) -> int:
    settings = get_settings()
    cache_dir = Path(settings.pipeline_cache_dir)
    h = _pdf_hash(pdf_path)
    removed = 0
    for f in cache_dir.glob(f"gemini_{h}*.md"):
        f.unlink()
        removed += 1
    return removed


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


def _running_jobs_for_textbook(textbook_id: str) -> list[str]:
    """Return job_ids currently running for this textbook (best-effort scan)."""
    import redis
    from urllib.parse import urlparse

    s = get_settings()
    u = urlparse(s.redis_url)
    r = redis.Redis(host=u.hostname or "localhost", port=u.port or 6379,
                    db=int((u.path or "/0").lstrip("/") or "0"), decode_responses=True)
    running: list[str] = []
    for key in r.scan_iter("job:*"):
        data = r.hgetall(key)
        if data.get("status") == "running" and data.get("textbook_id") == textbook_id:
            running.append(key.replace("job:", ""))
    return running


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="Re-ingest all textbooks in ALL_TEXTBOOKS")
    ap.add_argument(
        "--ready",
        action="store_true",
        help="Re-ingest only READY_KEYS (books with complete exercise-range tables)",
    )
    ap.add_argument("--keys", default="", help="Comma-separated keys, e.g. g6_vilenkin,g6_local")
    ap.add_argument("--grades", default="", help="Legacy: one book per grade (5,6,7)")
    ap.add_argument("--skip-keys", default="", help="Skip keys even in --all")
    ap.add_argument("--skip-running", action="store_true",
                    help="Skip textbooks that already have a running job")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-clear", action="store_true")
    args = ap.parse_args()

    skip = set(SKIP_KEYS)
    if args.skip_keys:
        skip |= {k.strip() for k in args.skip_keys.split(",") if k.strip()}

    selected: list[dict] = []
    if args.ready:
        selected = [_by_key(k) for k in READY_KEYS]
        selected = [tb for tb in selected if tb is not None]
    elif args.all:
        selected = [tb for tb in ALL_TEXTBOOKS if tb["key"] not in skip]
    elif args.keys:
        for key in [k.strip() for k in args.keys.split(",") if k.strip()]:
            if key in FINISHED_KEYS:
                print(f"[SKIP] {key} — digitization finished, will not re-ingest")
                continue
            tb = _by_key(key)
            if tb and key not in skip:
                selected.append(tb)
            elif not tb:
                print(f"[WARN] Unknown key: {key}")
    elif args.grades:
        grades = {int(g.strip()) for g in args.grades.split(",") if g.strip()}
        seen: set[int] = set()
        for tb in ALL_TEXTBOOKS:
            if tb["class_level"] in grades and tb["class_level"] not in seen:
                if tb["key"] not in skip:
                    selected.append(tb)
                    seen.add(tb["class_level"])
    else:
        selected = [_by_key(READY_KEYS[0])]  # default: first READY key (g6_local)

    print("=" * 70)
    print("  FULL RE-INGEST — MAX QUALITY (upgraded pipeline)")
    print("=" * 70)
    print(f"  Queue: {len(selected)} textbook(s)")

    engine = create_engine(get_settings().database_url)
    job_ids: list[tuple[str, str]] = []

    for tb in selected:
        pdf = Path(tb["pdf"])
        if not pdf.exists():
            print(f"\n[SKIP] {tb['title']} — PDF not found: {pdf}")
            continue

        if args.skip_running:
            running = _running_jobs_for_textbook(tb["id"])
            if running:
                print(f"\n[SKIP] {tb['title']} — already running: {running[0]}")
                continue

        print(f"\n▸ {tb['title']}")
        print(f"  key: {tb['key']}")
        print(f"  id : {tb['id']}")
        print(f"  pdf: {tb['pdf']}")

        if args.dry_run:
            continue

        with engine.begin() as conn:
            if not args.no_clear:
                n_tasks = clear_textbook(conn, tb["id"])
                n_cache = clear_ocr_cache(tb["pdf"])
                print(f"  cleared: {n_tasks} tasks, {n_cache} OCR cache files")

        job_id = str(uuid.uuid4())
        JobStateManager().create(
            job_id=job_id,
            textbook_id=tb["id"],
            class_level=tb["class_level"],
            source_type="pdf",
            source_path=tb["pdf"],
        )
        job_ids.append((tb["title"], job_id))
        print(f"  job_id: {job_id}")

    if args.dry_run:
        print("\n[DRY-RUN] No changes made.")
        return 0

    if job_ids:
        if len(job_ids) == 1:
            clear_arq_digitization_queue()
        for title, jid in job_ids:
            asyncio.run(enqueue_digitization(jid))
            print(f"  ARQ enqueued: {title} → {jid}")

    print("\n" + "=" * 70)
    print("  Jobs (watch with report_job.py):")
    for title, jid in job_ids:
        print(f"    [{title}]")
        print(f"      docker exec content-worker python /app/scripts/report_job.py {jid} --watch")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
