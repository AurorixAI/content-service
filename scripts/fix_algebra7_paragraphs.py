#!/usr/bin/env python3
"""
Fix §1, §21, §26 for «Алгебра 7 класс» (Uzbek).

Problem: a prior failed run left wrong Makarychev-style tasks (global ex numbers
470+, 601+) and §1 ghost rows blocking ON CONFLICT on task ids G7_TB_1_*.

Steps:
  1. Delete all tasks for paragraphs 1, 21, 26
  2. Clear OCR cache for those page ranges
  3. Enqueue targeted content-first re-extract job

Usage:
    docker exec content-worker python /app/scripts/fix_algebra7_paragraphs.py
    docker exec content-worker python /app/scripts/fix_algebra7_paragraphs.py --dry-run
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

TEXTBOOK_ID = "4b19752a-3d54-4538-b6a6-26ce1fbb48fd"
PDF = "/textbooks/7_grade/Алгебра 7 класс.pdf"
PARAGRAPHS = ["1", "21", "26"]
EXPECTED = {"1": 9, "21": 8, "26": 12}


def _pdf_hash(pdf_path: str) -> str:
    return hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:16]


def _page_end(conn, number: str, page_start: int) -> int:
    row = conn.execute(
        text("""
            SELECT page_start FROM textbook_toc
            WHERE textbook_id = CAST(:tid AS UUID) AND level = 2
              AND number::text > :n
            ORDER BY number::text LIMIT 1
        """),
        {"tid": TEXTBOOK_ID, "n": number},
    ).fetchone()
    if row and row.page_start:
        return int(row.page_start) - 1
    import fitz
    return len(fitz.open(PDF))


def clear_tasks(conn, paragraphs: list[str]) -> int:
    ids = conn.execute(
        text("""
            SELECT tm.id FROM tasks_master tm
            JOIN textbook_tasks tt ON tt.task_id = tm.id
            WHERE tt.textbook_id = CAST(:tid AS UUID)
              AND tt.paragraph_number = ANY(:nums)
        """),
        {"tid": TEXTBOOK_ID, "nums": paragraphs},
    ).fetchall()
    if not ids:
        return 0
    task_ids = [r[0] for r in ids]
    conn.execute(
        text("DELETE FROM task_figure_refs WHERE task_id = ANY(:ids)"),
        {"ids": task_ids},
    )
    conn.execute(
        text("DELETE FROM textbook_tasks WHERE textbook_id = CAST(:tid AS UUID) AND paragraph_number = ANY(:nums)"),
        {"tid": TEXTBOOK_ID, "nums": paragraphs},
    )
    r = conn.execute(
        text("DELETE FROM tasks_master WHERE id = ANY(:ids)"),
        {"ids": task_ids},
    )
    return r.rowcount


def clear_ocr_cache(conn, paragraphs: list[str]) -> int:
    settings = get_settings()
    cache_dir = Path(settings.pipeline_cache_dir)
    file_hash = _pdf_hash(PDF)
    removed = 0
    for p in paragraphs:
        row = conn.execute(
            text("""
                SELECT page_start, page_end FROM textbook_toc
                WHERE textbook_id = CAST(:tid AS UUID)
                  AND level = 2 AND number = :n
            """),
            {"tid": TEXTBOOK_ID, "n": p},
        ).fetchone()
        if not row or not row.page_start:
            print(f"  [WARN] §{p}: no TOC entry")
            continue
        p_start = int(row.page_start)
        p_end = int(row.page_end) if row.page_end else _page_end(conn, p, p_start)
        cache_file = cache_dir / f"gemini_{file_hash}_p{p_start}-{p_end}.md"
        if cache_file.exists():
            cache_file.unlink()
            print(f"  [OK] cleared OCR cache §{p} p{p_start}-{p_end}")
            removed += 1
        else:
            print(f"  [--] no cache §{p} p{p_start}-{p_end}")
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


def audit(conn) -> None:
    print("\n=== BEFORE/AFTER audit ===")
    for p in PARAGRAPHS:
        row = conn.execute(
            text("""
                SELECT COUNT(*) AS cnt,
                       array_agg(tt.exercise_number ORDER BY tt.exercise_number::int) AS ex_nums
                FROM textbook_tasks tt
                WHERE tt.textbook_id = CAST(:tid AS UUID)
                  AND tt.paragraph_number = :p
            """),
            {"tid": TEXTBOOK_ID, "p": p},
        ).fetchone()
        cnt = row.cnt or 0
        exp = EXPECTED[p]
        status = "OK" if cnt == exp else f"GAP ({cnt}/{exp})"
        print(f"  §{p}: {cnt} tasks (expected {exp}) — {status}")
        if row.ex_nums and cnt <= 15:
            print(f"       exercises: {row.ex_nums}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        print("=== Current state ===")
        audit(conn)

        preview = conn.execute(
            text("""
                SELECT tt.paragraph_number, COUNT(*) AS cnt
                FROM textbook_tasks tt
                WHERE tt.textbook_id = CAST(:tid AS UUID)
                  AND tt.paragraph_number = ANY(:nums)
                GROUP BY tt.paragraph_number ORDER BY tt.paragraph_number::int
            """),
            {"tid": TEXTBOOK_ID, "nums": PARAGRAPHS},
        ).fetchall()
        print(f"\nTasks to delete: {sum(r.cnt for r in preview)} across §{PARAGRAPHS}")
        for r in preview:
            print(f"  §{r.paragraph_number}: {r.cnt} wrong/ghost tasks")

    if args.dry_run:
        print("\n[DRY-RUN] No changes.")
        return 0

    with engine.begin() as conn:
        n = clear_tasks(conn, PARAGRAPHS)
        print(f"\n[OK] Deleted {n} tasks for §{PARAGRAPHS}")

    with engine.connect() as conn:
        print("\n=== Clearing OCR cache ===")
        clear_ocr_cache(conn, PARAGRAPHS)

    job_id = str(uuid.uuid4())
    JobStateManager().create(
        job_id=job_id,
        textbook_id=TEXTBOOK_ID,
        class_level=7,
        source_type="pdf",
        source_path=PDF,
        content_first=True,
        target_paragraphs=PARAGRAPHS,
    )
    asyncio.run(_enqueue(job_id))
    print(f"\n[OK] Job enqueued: {job_id}")
    print(f"     target §: {', '.join(PARAGRAPHS)}")
    print(f"     watch: docker logs content-worker -f 2>&1 | grep {job_id[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
