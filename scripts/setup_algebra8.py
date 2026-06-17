#!/usr/bin/env python3
"""Register «Алгebра 8 — Школьное издание» and insert TOC."""
from __future__ import annotations

import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

import arq
from urllib.parse import urlparse

from src.core.config import get_settings
from src.core.job_state import JobStateManager
from src.pipeline.db_writer import DBWriter

TEXTBOOK_ID = "e8f3a1b2-7c4d-5e6f-8091-2345678abcde"
PDF = "/textbooks/8_grade/www.idum.uz__algebra_8_rus.pdf"


def main() -> int:
    writer = DBWriter()
    writer.upsert_textbook(
        textbook_id=TEXTBOOK_ID,
        title="Алгебра 8 класс — Школьное издание",
        authors=["Ш.А. Алимов", "А.Р. Халмухамедов", "М.А. Мирзахмедов"],
        class_level=8,
        subtitle="O'qituvchi, 2019",
        publisher="O'qituvchi",
        edition="4-е издание",
        country="UZ",
        language="ru",
        total_pages=240,
    )
    print(f"[OK] textbook registered: {TEXTBOOK_ID}")

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "insert_toc_algebra8", "/app/scripts/insert_toc_algebra8.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    n = writer.write_toc(TEXTBOOK_ID, mod.TOC)
    print(f"[OK] TOC: {n} entries")

    job_id = str(uuid.uuid4())
    JobStateManager().create(
        job_id=job_id,
        textbook_id=TEXTBOOK_ID,
        class_level=8,
        source_type="pdf",
        source_path=PDF,
    )
    u = urlparse(get_settings().redis_url)

    async def go() -> None:
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

    asyncio.run(go())
    print(f"[OK] digitization job: {job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
