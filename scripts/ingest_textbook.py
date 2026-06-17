#!/usr/bin/env python3
"""Ingest a textbook end-to-end: TOC extraction → DB registration → digitization job.

Запускается ВНУТРИ контейнера content-worker (там есть PyMuPDF, Gemini ADC,
доступ к БД и Redis). На хосте:

    docker exec content-worker python /app/scripts/ingest_textbook.py \\
        --pdf /textbooks/5_grade/matematika_1qism_5_rus.pdf \\
        --title "Математика, 5 класс (IDUM, 2020) — часть 1" \\
        --class 5 \\
        --authors "Авторский коллектив IDUM" \\
        --publisher "IDUM" \\
        --language ru --country UZ

После создания job-скрипт выводит job_id; статус — `GET /api/v1/jobs/{id}`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

# scripts/ выполняется как python -m, путь /app/scripts/...
sys.path.insert(0, "/app")

import arq  # noqa: E402
import fitz  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.job_state import JobStateManager  # noqa: E402
from src.pipeline.db_writer import DBWriter  # noqa: E402
from src.pipeline.toc_extractor import extract_toc  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ingest")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd")

    # ── ingest (default, positional-less) ───────────────────────────────────
    ing = sub.add_parser("ingest", help="Full ingest: TOC + register + job")
    _add_ingest_args(ing)

    # ── update-toc ────────────────────────────────────────────────────────────
    utoc = sub.add_parser("update-toc", help="Re-extract TOC and write to existing textbook")
    utoc.add_argument("--textbook-id", required=True)
    utoc.add_argument("--pdf", required=True)
    utoc.add_argument("--force-llm-toc", action="store_true")

    # support calling without subcommand (backward compat)
    _add_ingest_args(p)
    return p.parse_args()


def _add_ingest_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--pdf", required=False)
    p.add_argument("--title", required=False)
    p.add_argument("--class", dest="class_level", type=int, choices=range(5, 12))
    p.add_argument("--authors", nargs="*", default=[])
    p.add_argument("--subtitle", default=None)
    p.add_argument("--publisher", default=None)
    p.add_argument("--isbn", default=None)
    p.add_argument("--edition", default=None)
    p.add_argument("--language", default="ru")
    p.add_argument("--country", default="UZ")
    p.add_argument("--subject", default="math")
    p.add_argument(
        "--force-llm-toc",
        action="store_true",
        help="Ignore PDF bookmarks, always call Gemini Pro Vision",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only extract TOC and print — no DB writes, no job",
    )


def _arq_redis_settings():
    s = get_settings()
    # Парсим redis://host:port/db
    from urllib.parse import urlparse
    u = urlparse(s.redis_url)
    return arq.connections.RedisSettings(
        host=u.hostname or "localhost",
        port=u.port or 6379,
        database=int((u.path or "/0").lstrip("/") or "0"),
    )


async def _enqueue_job(job_id: str) -> None:
    pool = await arq.create_pool(_arq_redis_settings())
    try:
        await pool.enqueue_job("run_digitization_job", job_id)
    finally:
        await pool.aclose()


def main() -> int:
    args = parse_args()

    # ── update-toc subcommand ─────────────────────────────────────────────────
    if getattr(args, "cmd", None) == "update-toc":
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            log.error("PDF not found: %s", pdf_path)
            return 1
        toc_entries = extract_toc(str(pdf_path), force_llm=args.force_llm_toc)
        log.info("TOC: %d entries extracted", len(toc_entries))
        if not toc_entries:
            log.error("No TOC entries — aborting update")
            return 1
        writer = DBWriter()
        n = writer.write_toc(args.textbook_id, toc_entries)
        log.info("Wrote %d TOC entries for textbook %s", n, args.textbook_id)
        return 0

    # ── ingest (default) ──────────────────────────────────────────────────────
    if not args.pdf or not args.title or not args.class_level:
        log.error("--pdf, --title, --class are required for ingest")
        return 1

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        log.error("PDF not found: %s", pdf_path)
        return 1

    # Page count для total_pages
    try:
        with fitz.open(str(pdf_path)) as doc:
            total_pages = doc.page_count
    except Exception as exc:
        log.error("Cannot open PDF: %s", exc)
        return 1

    log.info("=== %s (%d стр.) ===", args.title, total_pages)

    # 1. TOC
    log.info("Step 1/3: extracting TOC...")
    toc_entries = extract_toc(str(pdf_path), force_llm=args.force_llm_toc)
    log.info("TOC: %d entries", len(toc_entries))
    if toc_entries:
        for e in toc_entries[:5]:
            log.info("  %s%s %s (стр.%s)",
                     "  " * (e.get("level", 1) - 1),
                     e.get("number"), e.get("title"), e.get("page_start"))
        if len(toc_entries) > 5:
            log.info("  ... (+%d ещё)", len(toc_entries) - 5)

    if args.dry_run:
        print(json.dumps(toc_entries, ensure_ascii=False, indent=2))
        return 0

    # 2. Register textbook + TOC
    log.info("Step 2/3: registering textbook in DB...")
    textbook_id = str(uuid.uuid4())
    writer = DBWriter()
    writer.upsert_textbook(
        textbook_id=textbook_id,
        title=args.title,
        class_level=args.class_level,
        authors=args.authors or [],
        subtitle=args.subtitle,
        publisher=args.publisher,
        isbn=args.isbn,
        edition=args.edition,
        total_pages=total_pages,
        cover_image_url=None,
        subject=args.subject,
        country=args.country,
        language=args.language,
    )
    toc_written = writer.write_toc(textbook_id, toc_entries) if toc_entries else 0
    log.info("Textbook registered: %s (TOC %d entries)", textbook_id, toc_written)

    # 3. Create + enqueue digitization job
    log.info("Step 3/3: creating digitization job...")
    job_id = str(uuid.uuid4())
    state = JobStateManager()
    state.create(
        job_id=job_id,
        textbook_id=textbook_id,
        class_level=args.class_level,
        source_type="pdf",
        source_path=str(pdf_path),
    )
    asyncio.run(_enqueue_job(job_id))

    print()
    print("=" * 60)
    print(f"  textbook_id = {textbook_id}")
    print(f"  job_id      = {job_id}")
    print(f"  status URL  = http://localhost:8004/api/v1/jobs/{job_id}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
