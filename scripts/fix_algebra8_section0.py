#!/usr/bin/env python3
"""Re-extract §0 G8 — split 1), 2), 3) sub-items into separate tasks."""
from __future__ import annotations

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


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)

    with engine.begin() as conn:
        r = conn.execute(
            text("""
                DELETE FROM textbook_tasks
                WHERE textbook_id = CAST(:tid AS UUID)
                  AND toc_id IN (
                    SELECT id FROM textbook_toc
                    WHERE textbook_id = CAST(:tid AS UUID) AND number = '0'
                  )
            """),
            {"tid": TEXTBOOK_ID},
        )
        print(f"deleted textbook_tasks: {r.rowcount}")
        r2 = conn.execute(
            text("""
                DELETE FROM tasks_master
                WHERE id LIKE 'G8_ALG_0_%'
            """),
        )
        print(f"deleted tasks_master: {r2.rowcount}")

    file_hash = hashlib.sha256(Path(PDF).read_bytes()).hexdigest()[:16]
    cache_dir = Path(settings.pipeline_cache_dir)
    for page in range(3, 7):
        for pat in [f"gemini_{file_hash}_p{page}-{page}.md", f"gemini_{file_hash}_p3-6.md"]:
            p = cache_dir / pat
            if p.exists():
                p.unlink()
                print(f"cleared {p.name}")

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, number, title, page_start, page_end
                FROM textbook_toc
                WHERE textbook_id = CAST(:tid AS UUID) AND number = '0'
            """),
            {"tid": TEXTBOOK_ID},
        ).fetchone()

    entry = {
        "id": str(row.id),
        "number": row.number,
        "title": row.title,
        "page_start": int(row.page_start),
        "page_end": int(row.page_end),
    }

    ocr = GeminiVisionOCR()
    head = ocr.process_pages(PDF, 1, 10, figures_by_page={})
    legend = LegendExtractor().extract_legend(head)
    extractor = TaskExtractor(legend=legend)
    mapper = SkeletonTextbookMapper()
    mapper.load_skills_from_db(settings.database_url, class_level=8)
    fig_extractor = FigureExtractor(TEXTBOOK_ID)
    orch = DigitizationOrchestrator(
        job_id=f"fix_s0_{uuid.uuid4().hex[:8]}",
        textbook_id=TEXTBOOK_ID,
        class_level=8,
    )

    n = orch._process_paragraph_pages(
        entry=entry,
        pdf_path=PDF,
        fig_extractor=fig_extractor,
        ocr_worker=ocr,
        extractor=extractor,
        mapper=mapper,
        theme_stream=True,
    )
    print(f"§0 re-extract: +{n} tasks")

    with engine.connect() as conn:
        cnt = conn.execute(
            text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc tt ON tt.id = tm.toc_id
                WHERE tt.textbook_id = CAST(:tid AS UUID) AND tt.number = '0'
            """),
            {"tid": TEXTBOOK_ID},
        ).scalar()
    print(f"§0 total in DB: {cnt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
