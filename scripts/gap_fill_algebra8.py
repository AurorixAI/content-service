#!/usr/bin/env python3
"""
Gap-fill for «Алгebра 8 класс — Школьное издание» (IDUM, theme-stream).

Auto-detects § with ≤ threshold tasks, clears OCR cache, re-extracts via
_process_paragraph_pages (theme_stream=True).

Usage:
    docker exec content-worker python /app/scripts/gap_fill_algebra8.py
    docker exec content-worker python /app/scripts/gap_fill_algebra8.py --dry-run
    docker exec content-worker python /app/scripts/gap_fill_algebra8.py --threshold 5
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import uuid
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.classification import SkeletonTextbookMapper
from src.pipeline.extraction import LegendExtractor, TaskExtractor
from src.pipeline.figures import FigureExtractor
from src.pipeline.ocr import GeminiVisionOCR
from src.pipeline.orchestrator import DigitizationOrchestrator

TEXTBOOK_ID = "e8f3a1b2-7c4d-5e6f-8091-2345678abcde"
PDF = "/textbooks/8_grade/www.idum.uz__algebra_8_rus.pdf"
CLASS_LEVEL = 8


def _pdf_hash() -> str:
    return hashlib.sha256(Path(PDF).read_bytes()).hexdigest()[:16]


def find_gaps(threshold: int) -> list[dict]:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT t.id, t.number, t.title, t.page_start, t.page_end, t.sort_order,
                       COUNT(tm.id) AS cnt
                FROM textbook_toc t
                LEFT JOIN tasks_master tm ON tm.toc_id = t.id
                WHERE t.textbook_id = CAST(:tid AS UUID) AND t.level = 2
                GROUP BY t.id, t.number, t.title, t.page_start, t.page_end, t.sort_order
                ORDER BY t.sort_order
            """),
            {"tid": TEXTBOOK_ID},
        ).fetchall()

    all_starts = [(r[0], r[3]) for r in rows]
    gaps: list[dict] = []
    for i, row in enumerate(rows):
        toc_id, number, title, page_start, page_end, _sort, cnt = row
        if cnt > threshold or page_start is None:
            continue
        pe = page_end
        if pe is None:
            pe = page_start
            for j in range(i + 1, len(rows)):
                ns = rows[j][3]
                if ns is not None and ns > page_start:
                    pe = ns - 1
                    break
        gaps.append({
            "id": str(toc_id),
            "number": number,
            "title": title,
            "page_start": int(page_start),
            "page_end": int(pe),
            "tasks": int(cnt),
        })
    return gaps


def clear_cache(gaps: list[dict]) -> int:
    cache_dir = Path(get_settings().pipeline_cache_dir)
    file_hash = _pdf_hash()
    removed = 0
    for g in gaps:
        ps, pe = g["page_start"], g["page_end"]
        cf = cache_dir / f"gemini_{file_hash}_p{ps}-{pe}.md"
        if cf.exists():
            cf.unlink()
            print(f"  cleared cache §{g['number']} p{ps}-{pe}")
            removed += 1
        for page in range(ps, pe + 1):
            pf = cache_dir / f"gemini_{file_hash}_p{page}-{page}.md"
            if pf.exists():
                pf.unlink()
                removed += 1
    return removed


def run_gap_fill(gaps: list[dict]) -> int:
    settings = get_settings()
    ocr = GeminiVisionOCR()
    legend: dict = {}
    try:
        head = ocr.process_pages(PDF, 1, 10, figures_by_page={})
        legend = LegendExtractor().extract_legend(head)
        print(f"Legend: {len(legend)} markers")
    except Exception as exc:
        print(f"Legend failed: {exc}")

    extractor = TaskExtractor(legend=legend)
    mapper = SkeletonTextbookMapper()
    mapper.load_skills_from_db(settings.database_url, class_level=CLASS_LEVEL)
    fig_extractor = FigureExtractor(TEXTBOOK_ID)
    job_id = f"g8_gap_{uuid.uuid4().hex[:8]}"
    orch = DigitizationOrchestrator(
        job_id=job_id,
        textbook_id=TEXTBOOK_ID,
        class_level=CLASS_LEVEL,
    )

    total = 0
    for entry in gaps:
        print(f"\n§{entry['number']} p{entry['page_start']}-{entry['page_end']} "
              f"({entry['tasks']} tasks) …")
        try:
            n = orch._process_paragraph_pages(
                entry=entry,
                pdf_path=PDF,
                fig_extractor=fig_extractor,
                ocr_worker=ocr,
                extractor=extractor,
                mapper=mapper,
                theme_stream=True,
            )
            print(f"  → +{n} tasks")
            total += n
        except Exception as exc:
            print(f"  → FAILED: {exc}")
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--threshold", type=int, default=0,
                    help="Re-extract § with ≤ N tasks (default: 0 = empty only)")
    args = ap.parse_args()

    gaps = find_gaps(args.threshold)
    if not gaps:
        print("No gaps — nothing to fill.")
        return 0

    print(f"Gap-fill G8: {len(gaps)} § (threshold ≤ {args.threshold})\n")
    for g in gaps:
        print(f"  §{g['number']:>2s}  p{g['page_start']:>3d}-{g['page_end']:<3d}  "
              f"{g['tasks']:>3d} tasks  {(g['title'] or '')[:45]}")

    if args.dry_run:
        print("\n[DRY-RUN] skipped")
        return 0

    print(f"\nClearing OCR cache …")
    n_cache = clear_cache(gaps)
    print(f"  {n_cache} cache file(s) removed\n")

    total = run_gap_fill(gaps)
    print(f"\nDone: +{total} tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
