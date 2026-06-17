#!/usr/bin/env python3
"""Targeted content-first gap-fill for «Алгебра 7 класс» paragraphs with missing exercises."""
from __future__ import annotations

import asyncio
import hashlib
import sys
import uuid
from pathlib import Path

sys.path.insert(0, "/app")

import arq
from sqlalchemy import create_engine, text
from urllib.parse import urlparse

from src.core.config import get_settings
from src.core.job_state import JobStateManager

TEXTBOOK_ID = "4b19752a-3d54-4538-b6a6-26ce1fbb48fd"
PDF = "/textbooks/7_grade/Алгебра 7 класс.pdf"
GAPS = ["0", "2", "4", "10", "14", "24", "28", "29", "30", "31", "32", "34", "35", "37", "39"]


def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    file_hash = hashlib.sha256(Path(PDF).read_bytes()).hexdigest()[:16]
    cache_dir = Path(settings.pipeline_cache_dir)

    with engine.connect() as conn:
        for p in GAPS:
            row = conn.execute(
                text("""
                    SELECT page_start, page_end FROM textbook_toc
                    WHERE textbook_id = CAST(:tid AS UUID) AND level = 2 AND number = :n
                """),
                {"tid": TEXTBOOK_ID, "n": p},
            ).fetchone()
            if not row or not row.page_start:
                print(f"§{p}: no TOC entry")
                continue
            ps = int(row.page_start)
            pe = int(row.page_end or ps)
            cf = cache_dir / f"gemini_{file_hash}_p{ps}-{pe}.md"
            if cf.exists():
                cf.unlink()
                print(f"cleared cache §{p} p{ps}-{pe}")
            else:
                print(f"no cache §{p} p{ps}-{pe}")

    job_id = str(uuid.uuid4())
    JobStateManager().create(
        job_id=job_id,
        textbook_id=TEXTBOOK_ID,
        class_level=7,
        source_type="pdf",
        source_path=PDF,
        content_first=True,
        target_paragraphs=GAPS,
    )

    u = urlparse(settings.redis_url)

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
    print(f"gap-fill job: {job_id}")
    print(f"paragraphs ({len(GAPS)}): {', '.join(GAPS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
