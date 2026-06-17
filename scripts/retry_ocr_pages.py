#!/usr/bin/env python3
"""Re-OCR specific PDF pages (invalidate cache + retries).

Usage:
    docker exec content-worker python /app/scripts/retry_ocr_pages.py \\
        --pdf "/textbooks/6_grade/6 класс математика школа.pdf" \\
        --pages 36,86,169,186,193
"""
from __future__ import annotations

import argparse
import sys
import time

sys.path.insert(0, "/app")

from src.pipeline.ocr import GeminiVisionOCR
from src.pipeline.ocr_utils import is_usable_ocr_text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", required=True, help="Comma-separated 1-based page numbers")
    ap.add_argument("--attempts", type=int, default=4)
    args = ap.parse_args()

    pages = [int(p.strip()) for p in args.pages.split(",") if p.strip()]
    ocr = GeminiVisionOCR()
    failed: list[int] = []

    for page in pages:
        ocr.invalidate_pages_cache(args.pdf, page, page)
        ok = False
        for attempt in range(1, args.attempts + 1):
            if attempt > 1:
                wait = 25 * attempt
                print(f"  p{page}: retry {attempt}/{args.attempts} in {wait}s…")
                time.sleep(wait)
            text = ocr.process_pages(
                args.pdf, page, page, figures_by_page={}, force_refresh=True,
            )
            if is_usable_ocr_text(text):
                print(f"[OK] p{page}: {len(text)} chars (attempt {attempt})")
                ok = True
                break
            ocr.invalidate_pages_cache(args.pdf, page, page)
        if not ok:
            print(f"[FAIL] p{page}: still unusable after {args.attempts} attempts")
            failed.append(page)

    if failed:
        print(f"Failed pages: {failed}")
        return 1
    print("All pages OCR OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
