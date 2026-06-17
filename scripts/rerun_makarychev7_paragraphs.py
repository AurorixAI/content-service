#!/usr/bin/env python3
"""Re-run digitization for specific Makarychev G7 paragraphs.

Clears per-range OCR cache (so Gemini re-OCRs), then enqueues a job.
Resume logic skips § that already have tasks in DB.

Usage:
    docker exec content-worker python /app/scripts/rerun_makarychev7_paragraphs.py \\
        --paragraphs 4,8,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46
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

TEXTBOOK_ID = "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f"
PDF = "/textbooks/7_grade/1701411287_algebra_-uchebnik_-7-kl_-makarychev_compressed.pdf"


def _pdf_hash(pdf_path: str) -> str:
    return hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:16]


def _page_end(conn, number: int, page_start: int) -> int:
    row = conn.execute(
        text("""
            SELECT page_start FROM textbook_toc
            WHERE textbook_id = CAST(:tid AS UUID) AND level = 2
              AND number::int > :n
            ORDER BY number::int LIMIT 1
        """),
        {"tid": TEXTBOOK_ID, "n": number},
    ).fetchone()
    if row and row.page_start:
        return row.page_start - 1
    import fitz

    return len(fitz.open(PDF))


def clear_ocr_cache(paragraphs: list[int]) -> int:
    settings = get_settings()
    cache_dir = Path(settings.pipeline_cache_dir)
    file_hash = _pdf_hash(PDF)
    engine = create_engine(settings.database_url)
    removed = 0

    with engine.connect() as conn:
        for p in paragraphs:
            row = conn.execute(
                text("""
                    SELECT page_start, page_end FROM textbook_toc
                    WHERE textbook_id = CAST(:tid AS UUID)
                      AND level = 2 AND number = :n
                """),
                {"tid": TEXTBOOK_ID, "n": str(p)},
            ).fetchone()
            if not row or not row.page_start:
                print(f"[WARN] §{p}: no page_start in TOC")
                continue
            p_start = int(row.page_start)
            p_end = int(row.page_end) if row.page_end else _page_end(conn, p, p_start)
            cache_file = cache_dir / f"gemini_{file_hash}_p{p_start}-{p_end}.md"
            if cache_file.exists():
                size = cache_file.stat().st_size
                cache_file.unlink()
                print(f"[OK] cleared OCR cache §{p} p{p_start}-{p_end} ({size} bytes)")
                removed += 1
            else:
                print(f"[--] no cache §{p} p{p_start}-{p_end}")

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--paragraphs",
        required=True,
        help="Comma-separated paragraph numbers, e.g. 4,8,27",
    )
    args = ap.parse_args()
    paragraphs = sorted({int(x.strip()) for x in args.paragraphs.split(",") if x.strip()})

    print(f"[INFO] Re-run {len(paragraphs)} paragraphs: {paragraphs}")
    n = clear_ocr_cache(paragraphs)
    print(f"[INFO] Cleared {n} OCR cache file(s)")

    job_id = str(uuid.uuid4())
    JobStateManager().create(
        job_id=job_id,
        textbook_id=TEXTBOOK_ID,
        class_level=7,
        source_type="pdf",
        source_path=PDF,
    )
    asyncio.run(_enqueue(job_id))
    print(f"[OK] Job enqueued: {job_id}")
    print(f"     watch: docker exec content-worker python /app/scripts/report_job.py {job_id} --watch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
