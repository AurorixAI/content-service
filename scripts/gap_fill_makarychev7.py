#!/usr/bin/env python3
"""
Targeted content-first gap-fill for Makarychev G7 (partial § only).

Detects § with missing exercises vs g7_makarychev.json ranges,
clears OCR cache, enqueues content-first re-extract job.

Usage:
    docker exec content-worker python /app/scripts/gap_fill_makarychev7.py
    docker exec content-worker python /app/scripts/gap_fill_makarychev7.py --dry-run
    docker exec content-worker python /app/scripts/gap_fill_makarychev7.py --min-gap 1
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, "/app")

import arq
from sqlalchemy import create_engine, text
from urllib.parse import urlparse

from src.core.config import get_settings
from src.core.job_state import JobStateManager

TEXTBOOK_ID = "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f"
PDF = "/textbooks/7_grade/1701411287_algebra_-uchebnik_-7-kl_-makarychev_compressed.pdf"
RANGES_FILE = "/app/data/exercise_ranges/g7_makarychev.json"


def _pdf_hash(pdf_path: str) -> str:
    return hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:16]


def _page_end(conn, number: str, page_start: int) -> int:
    row = conn.execute(
        text("""
            SELECT page_start FROM textbook_toc
            WHERE textbook_id = CAST(:tid AS UUID) AND level = 2
              AND number::int > CAST(:n AS INTEGER)
            ORDER BY number::int LIMIT 1
        """),
        {"tid": TEXTBOOK_ID, "n": number},
    ).fetchone()
    if row and row.page_start:
        return int(row.page_start) - 1
    import fitz
    return len(fitz.open(PDF))


def find_partial_paragraphs(min_gap: int = 1) -> list[tuple[str, int, int, list[int]]]:
    """Return [(para_num, have, expected, missing_sample), ...] sorted by gap size desc."""
    with open(RANGES_FILE) as f:
        ranges = {k: tuple(v) for k, v in json.load(f)["ranges"].items()}

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tt.paragraph_number::text AS p, tt.exercise_number::int AS ex
                FROM textbook_tasks tt
                WHERE tt.textbook_id = CAST(:tid AS UUID)
            """),
            {"tid": TEXTBOOK_ID},
        ).fetchall()

    from collections import defaultdict
    by: dict[str, set[int]] = defaultdict(set)
    for p, ex in rows:
        by[p].add(ex)

    partial: list[tuple[str, int, int, list[int]]] = []
    for pn in sorted(ranges.keys(), key=int):
        lo, hi = ranges[pn]
        expected = set(range(lo, hi + 1))
        have = by.get(pn, set())
        missing = sorted(expected - have)
        if len(missing) >= min_gap:
            partial.append((pn, len(have), len(expected), missing))

    partial.sort(key=lambda x: len(x[3]), reverse=True)
    return partial


def clear_ocr_cache(paragraphs: list[str]) -> int:
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
                {"tid": TEXTBOOK_ID, "n": p},
            ).fetchone()
            if not row or not row.page_start:
                print(f"  §{p}: no TOC entry")
                continue
            ps = int(row.page_start)
            pe = int(row.page_end) if row.page_end else _page_end(conn, p, ps)
            cf = cache_dir / f"gemini_{file_hash}_p{ps}-{pe}.md"
            if cf.exists():
                cf.unlink()
                print(f"  cleared cache §{p} p{ps}-{pe}")
                removed += 1
            else:
                print(f"  no cache §{p} p{ps}-{pe}")

    return removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-gap", type=int, default=1, help="Min missing exercises to include §")
    args = ap.parse_args()

    partial = find_partial_paragraphs(min_gap=args.min_gap)
    if not partial:
        print("No partial paragraphs — nothing to gap-fill.")
        return 0

    total_missing = sum(len(x[3]) for x in partial)
    print(f"Partial §: {len(partial)} | missing exercises: {total_missing}\n")
    for pn, have, exp, miss in partial:
        sample = miss[:6]
        tail = f"... +{len(miss)-6}" if len(miss) > 6 else ""
        print(f"  §{pn:>2s}: {have:3d}/{exp:3d}  missing {len(miss):3d}  {sample}{tail}")

    paragraphs = [p[0] for p in partial]

    if args.dry_run:
        print(f"\n[DRY-RUN] Would gap-fill {len(paragraphs)} §")
        return 0

    print(f"\nClearing OCR cache for {len(paragraphs)} § …")
    clear_ocr_cache(paragraphs)

    job_id = str(uuid.uuid4())
    JobStateManager().create(
        job_id=job_id,
        textbook_id=TEXTBOOK_ID,
        class_level=7,
        source_type="pdf",
        source_path=PDF,
        content_first=True,
        target_paragraphs=paragraphs,
    )

    u = urlparse(get_settings().redis_url)

    async def enqueue() -> None:
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

    asyncio.run(enqueue())
    print(f"\ngap-fill job: {job_id}")
    print(f"paragraphs ({len(paragraphs)}): {', '.join(paragraphs)}")
    print(f"watch: docker logs content-worker 2>&1 | grep {job_id[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
