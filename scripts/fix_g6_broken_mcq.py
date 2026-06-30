#!/usr/bin/env python3
"""Delete orphan-trim broken G6 MCQ tasks and re-extract from PDF pages."""
from __future__ import annotations

import argparse
import hashlib
import logging
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

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

TEXTBOOK_ID = "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8"
PDF = "/textbooks/6_grade/6 класс математика школа.pdf"
CLASS_LEVEL = 6

BROKEN_MCQ_IDS = [
    "G6_TB_19–20_174",
    "G6_TB_27–28_248",
    "G6_TB_98–100_862",
    "G6_TB_101–102_887",
    "G6_TB_110–112_953",
]

PARAGRAPHS = ["19–20", "27–28", "98–100", "101–102", "110–112"]


def delete_tasks(engine, task_ids: list[str]) -> int:
    if not task_ids:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM task_figure_refs WHERE task_id = ANY(:ids)"),
            {"ids": task_ids},
        )
        conn.execute(
            text("DELETE FROM textbook_tasks WHERE task_id = ANY(:ids)"),
            {"ids": task_ids},
        )
        n = conn.execute(
            text("DELETE FROM tasks_master WHERE id = ANY(:ids) RETURNING id"),
            {"ids": task_ids},
        ).rowcount
        conn.execute(
            text("""
                UPDATE textbooks SET tasks_extracted = (
                    SELECT COUNT(*) FROM textbook_tasks
                    WHERE textbook_id = CAST(:tid AS UUID)
                )
                WHERE textbook_id = CAST(:tid AS UUID)
            """),
            {"tid": TEXTBOOK_ID},
        )
    return n


def load_paragraph_entries(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, number, title, page_start, page_end, sort_order
                FROM textbook_toc
                WHERE textbook_id = CAST(:tid AS UUID)
                  AND number = ANY(:nums)
                ORDER BY sort_order
            """),
            {"tid": TEXTBOOK_ID, "nums": PARAGRAPHS},
        ).mappings().all()
        all_paras = conn.execute(
            text("""
                SELECT number, page_start, sort_order
                FROM textbook_toc
                WHERE textbook_id = CAST(:tid AS UUID)
                  AND page_start IS NOT NULL
                ORDER BY sort_order
            """),
            {"tid": TEXTBOOK_ID},
        ).mappings().all()

    by_sort = {r["number"]: dict(r) for r in all_paras}
    sorted_nums = [r["number"] for r in all_paras]
    entries: list[dict] = []
    for row in rows:
        number = row["number"]
        page_start = int(row["page_start"])
        page_end = row["page_end"]
        if page_end is None:
            idx = sorted_nums.index(number)
            page_end = page_start
            for j in range(idx + 1, len(sorted_nums)):
                ns = by_sort[sorted_nums[j]]["page_start"]
                if ns is not None and int(ns) > page_start:
                    page_end = int(ns) - 1
                    break
            else:
                page_end = page_start + 2
        entries.append({
            "id": str(row["id"]),
            "number": number,
            "title": row["title"] or "",
            "page_start": page_start,
            "page_end": int(page_end),
        })
    return entries


def invalidate_pages(pdf: str, pages: set[int]) -> None:
    settings = get_settings()
    cache_dir = Path(settings.pipeline_cache_dir)
    file_hash = hashlib.sha256(Path(pdf).read_bytes()).hexdigest()[:16]
    removed = 0
    for page in sorted(pages):
        for pat in cache_dir.glob(f"gemini_{file_hash}_*"):
            name = pat.name
            if f"_p{page}-" in name or name.endswith(f"_p{page}-{page}.md"):
                pat.unlink(missing_ok=True)
                removed += 1
    log.info("OCR cache invalidated for pages %s (%d files)", sorted(pages), removed)


def reocr_pages(pdf: str, pages: set[int]) -> None:
    ocr = GeminiVisionOCR()
    for page in sorted(pages):
        ocr.invalidate_pages_cache(pdf, page, page)
        text_out = ocr.process_pages(
            pdf, page, page, figures_by_page={}, force_refresh=True,
        )
        log.info("Re-OCR p%d: %d chars", page, len(text_out or ""))


def reextract_paragraphs(engine, entries: list[dict], *, dry_run: bool) -> int:
    if dry_run:
        for e in entries:
            log.info("[DRY] would re-extract §%s p%d–%d", e["number"], e["page_start"], e["page_end"])
        return 0

    settings = get_settings()
    ocr = GeminiVisionOCR()
    head = ocr.process_pages(PDF, 1, 10, figures_by_page={})
    legend = LegendExtractor().extract_legend(head)
    extractor = TaskExtractor(legend=legend)
    mapper = SkeletonTextbookMapper()
    mapper.load_skills_from_db(settings.database_url, class_level=CLASS_LEVEL)
    fig_extractor = FigureExtractor(TEXTBOOK_ID)
    orch = DigitizationOrchestrator(
        job_id=f"fix_mcq_{uuid.uuid4().hex[:8]}",
        textbook_id=TEXTBOOK_ID,
        class_level=CLASS_LEVEL,
    )

    total = 0
    for entry in entries:
        log.info("Re-extract §%s (p%d–%d)…", entry["number"], entry["page_start"], entry["page_end"])
        n = orch._process_paragraph_pages(
            entry=entry,
            pdf_path=PDF,
            fig_extractor=fig_extractor,
            ocr_worker=ocr,
            extractor=extractor,
            mapper=mapper,
            theme_stream=True,
        )
        log.info("  §%s: +%d tasks", entry["number"], n)
        total += n
    return total


def verify_restored(engine, exercise_nums: list[str]) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
                       tt.exercise_number
                FROM tasks_master tm
                JOIN textbook_tasks tt ON tt.task_id = tm.id
                WHERE tt.textbook_id = CAST(:tid AS UUID)
                  AND tt.exercise_number = ANY(:exs)
                ORDER BY tt.exercise_number
            """),
            {"tid": TEXTBOOK_ID, "exs": exercise_nums},
        ).mappings().all()
    log.info("Restored tasks: %d / %d", len(rows), len(exercise_nums))
    for r in rows:
        q = (r["question_text"] or "").replace("\n", " / ")[:140]
        log.info("  %s ex=%s type=%s ans=%s", r["id"], r["exercise_number"], r["answer_type"], r["correct_answer"])
        log.info("    Q: %s", q)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    entries = load_paragraph_entries(engine)
    pages = {e["page_start"] for e in entries}
    for e in entries:
        pages.update(range(e["page_start"], e["page_end"] + 1))

    log.info("Broken MCQ fix — %d tasks, %d paragraphs, pages %s",
             len(BROKEN_MCQ_IDS), len(entries), sorted(pages))

    if args.dry_run:
        for tid in BROKEN_MCQ_IDS:
            log.info("  [DRY] delete %s", tid)
        reextract_paragraphs(engine, entries, dry_run=True)
        return 0

    n_del = delete_tasks(engine, BROKEN_MCQ_IDS)
    log.info("Deleted %d tasks", n_del)

    invalidate_pages(PDF, pages)
    reocr_pages(PDF, pages)

    added = reextract_paragraphs(engine, entries, dry_run=False)
    log.info("Re-extract added %d tasks", added)

    verify_restored(engine, ["174", "248", "862", "887", "953"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
