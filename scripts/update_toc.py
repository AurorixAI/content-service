#!/usr/bin/env python3
"""
Скрипт: извлекает TOC из PDF и записывает в БД.
Использование: python3 /app/scripts/update_toc.py <textbook_id> <pdf_path>
"""
import sys
import json

sys.path.insert(0, "/app")

from src.pipeline.toc_extractor import extract_toc
from src.pipeline.db_writer import DBWriter as DbWriter
from src.core.config import get_settings

def main(textbook_id: str, pdf_path: str):
    print(f"[update_toc] PDF: {pdf_path}")
    print(f"[update_toc] Textbook ID: {textbook_id}")
    print("[update_toc] Extracting TOC via Gemini Vision...", flush=True)

    toc = extract_toc(pdf_path)
    print(f"[update_toc] Extracted {len(toc)} TOC entries", flush=True)

    if not toc:
        print("[update_toc] ERROR: no TOC extracted — check PDF quality", file=sys.stderr)
        sys.exit(1)

    print("[update_toc] TOC preview (first 10 entries):")
    for e in toc[:10]:
        print(f"  L{e['level']} | {e['number']:12s} | {e['title'][:60]:60s} | p.{e.get('page_start','?')}")

    settings = get_settings()
    writer = DbWriter()
    count = writer.write_toc(textbook_id, toc)
    print(f"[update_toc] Written {count} entries to DB for textbook {textbook_id}", flush=True)
    return count

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: update_toc.py <textbook_id> <pdf_path>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
