#!/usr/bin/env python3
"""Build exercise-range JSON tables from PDF + TOC (OCR scan).

Usage:
    docker exec content-worker python /app/scripts/build_exercise_ranges.py --all
    docker exec content-worker python /app/scripts/build_exercise_ranges.py --key g5_vilenkin
    docker exec content-worker python /app/scripts/build_exercise_ranges.py --all --cache-only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.exercise_ranges.registry import (
    _range_from_toc_number,
    parse_paragraph_key,
)
from src.pipeline.exercise_ranges.scan import (
    ResolvedRange,
    fill_sequential_gaps,
    resolve_paragraph_range,
)
from src.pipeline.makarychev7_exercise_ranges import (
    MAKARYCHEV7_EXERCISE_RANGES,
    MAKARYCHEV7_PAGE_END_OVERRIDE,
)
from src.pipeline.ocr import GeminiVisionOCR
from src.pipeline.ocr_utils import is_usable_ocr_text

OUT_DIR = Path("/app/data/exercise_ranges")

BOOKS: list[dict] = [
    {
        "key": "g5_vilenkin",
        "id": "184640af-64e7-47af-a974-8b8112e6ffb2",
        "pdf": "/textbooks/5_grade/vklasse_matematuka_5_klass_vilenkin_johov_chesnokov_shvarcbyrd_2013.pdf",
        "mode": "scan",
    },
    {
        "key": "g5_idum_ch1",
        "id": "5630a994-061d-4c20-9863-fe049c8059fb",
        "pdf": "/textbooks/5_grade/matematika_1qism_5_rus.pdf",
        "mode": "scan",
    },
    {
        "key": "g5_idum_ch2",
        "id": "47167115-5961-4405-bb55-1bda8ce1b687",
        "pdf": "/textbooks/5_grade/matematika_5_rus_2_chast_2020_www.idum.uz.pdf",
        "mode": "scan",
    },
    {
        "key": "g6_vilenkin",
        "id": "351a95c1-5208-4ae9-8323-6d7dd5e8bb82",
        "pdf": "/textbooks/6_grade/Виленкин 6 класс.pdf",
        "mode": "scan",
    },
    {
        "key": "g6_local",
        "id": "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8",
        "mode": "theme_stream",
    },
    {
        "key": "g7_makarychev",
        "id": "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f",
        "mode": "makarychev7",
    },
    {
        "key": "g7_algebra",
        "id": "4b19752a-3d54-4538-b6a6-26ce1fbb48fd",
        "pdf": "/textbooks/7_grade/Алгебра 7 класс.pdf",
        "mode": "scan",
    },
]


def _pdf_hash(pdf_path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _read_cache(pdf_path: str, p_start: int, p_end: int) -> str | None:
    import glob as glob_mod

    prefix = f"gemini_{_pdf_hash(pdf_path)}"
    parts: list[str] = []
    for cache in sorted(glob_mod.glob(f"/tmp/content_pipeline_cache/{prefix}_p*.md")):
        m = re.search(r"_p(\d+)-(\d+)\.md$", cache)
        if not m:
            continue
        batch_lo, batch_hi = int(m.group(1)), int(m.group(2))
        if batch_hi < p_start or batch_lo > p_end:
            continue
        t = Path(cache).read_text(encoding="utf-8")
        if is_usable_ocr_text(t):
            parts.append(t)
    if not parts:
        exact = Path(f"/tmp/content_pipeline_cache/{prefix}_p{p_start}-{p_end}.md")
        if exact.exists():
            t = exact.read_text(encoding="utf-8")
            return t if is_usable_ocr_text(t) else None
        return None
    return "\n\n".join(parts)


def load_leaf_toc(conn, textbook_id: str) -> list[dict]:
    rows = conn.execute(
        text("""
            WITH toc AS (
              SELECT id, number, title, page_start, page_end, level, parent_id, sort_order
              FROM textbook_toc
              WHERE textbook_id = CAST(:tid AS UUID)
            ),
            parents AS (
              SELECT DISTINCT parent_id AS id FROM toc WHERE parent_id IS NOT NULL
            )
            SELECT t.number, t.title, t.page_start, t.page_end, t.sort_order
            FROM toc t
            WHERE t.id NOT IN (SELECT id FROM parents)
              AND (t.level >= 2 OR t.page_start IS NOT NULL)
            ORDER BY t.sort_order, t.page_start
        """),
        {"tid": textbook_id},
    ).fetchall()
    return [
        {
            "number": r.number,
            "title": r.title,
            "page_start": r.page_start,
            "page_end": r.page_end,
        }
        for r in rows
    ]


def _compute_page_end(leaves: list[dict]) -> None:
    for i, entry in enumerate(leaves):
        if entry.get("page_end"):
            continue
        p_start = entry.get("page_start")
        if not p_start:
            continue
        next_start = None
        for nxt in leaves[i + 1:]:
            if nxt.get("page_start") and nxt["page_start"] > p_start:
                next_start = nxt["page_start"]
                break
        entry["page_end"] = (next_start - 1) if next_start else p_start + 4


def build_from_scan(
    conn,
    book: dict,
    *,
    cache_only: bool = False,
    ocr: GeminiVisionOCR | None = None,
) -> dict:
    leaves = load_leaf_toc(conn, book["id"])
    if not leaves:
        print(f"  [{book['key']}] WARNING: no TOC — empty ranges")
        return {"ranges": {}, "page_end_override": {}}

    _compute_page_end(leaves)
    pdf = book.get("pdf", "")
    ranges: dict[str, list[int]] = {}
    meta: dict[str, dict] = {}
    empty: list[str] = []
    prev_hi: int | None = None
    ordered_keys: list[str] = []

    for entry in leaves:
        key = parse_paragraph_key(entry["number"])
        ordered_keys.append(key)
        p_start = int(entry["page_start"] or 1)
        p_end = int(entry["page_end"] or p_start)

        text_content = _read_cache(pdf, p_start, p_end) if pdf else None
        if not text_content and not cache_only and pdf and ocr:
            print(f"  OCR §{key} p{p_start}-{p_end} …")
            text_content = ocr.process_pages(pdf, p_start, p_end, figures_by_page={})

        resolved = resolve_paragraph_range(text_content or "", prev_hi=prev_hi)
        if resolved:
            ranges[key] = [resolved.lo, resolved.hi]
            meta[key] = {
                "count": resolved.count,
                "method": resolved.method,
                "confidence": round(resolved.confidence, 2),
            }
            prev_hi = resolved.hi
            print(
                f"  §{key:<8} {resolved.lo:>4}–{resolved.hi:<4} "
                f"(×{resolved.count}, {resolved.method})  "
                f"{entry['title'][:36]}"
            )
        else:
            empty.append(key)
            print(f"  §{key:<8}  — no exercises  {entry['title'][:40]}")

    # Second pass: interpolate gaps between known global ranges
    if empty and ranges:
        before = len(ranges)
        filled: dict[str, tuple[int, int]] = {
            k: (v[0], v[1]) for k, v in ranges.items()
        }
        meta_resolved = {
            k: ResolvedRange(
                ranges[k][0], ranges[k][1],
                ranges[k][1] - ranges[k][0] + 1,
                meta[k]["method"], meta[k]["confidence"],
            )
            for k in ranges
        }
        filled = fill_sequential_gaps(ordered_keys, filled, meta=meta_resolved)
        for key, (lo, hi) in filled.items():
            if key not in ranges:
                ranges[key] = [lo, hi]
                meta[key] = {
                    "count": hi - lo + 1,
                    "method": "interpolated",
                    "confidence": 0.4,
                }
                print(f"  §{key:<8} {lo:>4}–{hi:<4} (interpolated gap fill)")
        if len(ranges) > before:
            empty = [k for k in empty if k not in ranges]
            prev_hi = max(hi for _, hi in filled.values())

    if empty:
        print(f"  [{book['key']}] {len(empty)} § still empty: {empty[:12]}")
    return {"ranges": ranges, "page_end_override": {}, "meta": meta}


def build_from_toc_number(conn, book: dict) -> dict:
    leaves = load_leaf_toc(conn, book["id"])
    ranges: dict[str, list[int]] = {}
    for entry in leaves:
        key = parse_paragraph_key(entry["number"])
        rng = _range_from_toc_number(key)
        if rng:
            ranges[key] = [rng[0], rng[1]]
    print(f"  [{book['key']}] {len(ranges)} ranges from TOC numbers")
    return {"ranges": ranges, "page_end_override": {}}


def build_makarychev(book: dict) -> dict:
    ranges = {str(k): [v[0], v[1]] for k, v in MAKARYCHEV7_EXERCISE_RANGES.items()}
    override = {str(k): v for k, v in MAKARYCHEV7_PAGE_END_OVERRIDE.items()}
    print(f"  [{book['key']}] {len(ranges)} ranges from makarychev7 table")
    return {"ranges": ranges, "page_end_override": override}


def write_json(book: dict, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "textbook_id": book["id"],
        "key": book["key"],
        "numbering": book.get("mode", "scan"),
        **payload,
    }
    path = OUT_DIR / f"{book['key']}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → wrote {path} ({len(payload.get('ranges', {}))} §)")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--key", default="")
    ap.add_argument("--cache-only", action="store_true", help="Use OCR cache only, no live OCR")
    args = ap.parse_args()

    if args.all:
        selected = BOOKS
    elif args.key:
        selected = [b for b in BOOKS if b["key"] == args.key]
        if not selected:
            print(f"Unknown key: {args.key}")
            return 1
    else:
        ap.print_help()
        return 1

    engine = create_engine(get_settings().database_url)
    ocr = None if args.cache_only else GeminiVisionOCR()

    with engine.connect() as conn:
        for book in selected:
            print(f"\n=== {book['key']} ===")
            mode = book.get("mode", "scan")
            if mode == "makarychev7":
                payload = build_makarychev(book)
            elif mode == "toc_number":
                payload = build_from_toc_number(conn, book)
            elif mode == "theme_stream":
                payload = {
                    "textbook_id": book["id"],
                    "key": book["key"],
                    "numbering": "theme_stream",
                    "ranges": {},
                    "note": "§ boundaries from theme headers in OCR; no exercise-range filter",
                }
                out = OUT_DIR / f"{book['key']}.json"
                out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  → wrote {out} (theme_stream — no numeric ranges)")
                continue
            else:
                payload = build_from_scan(
                    conn, book, cache_only=args.cache_only, ocr=ocr,
                )
            write_json(book, payload)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
