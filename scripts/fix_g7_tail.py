#!/usr/bin/env python3
"""Fix G7 tail: 3 stuck reprocess text tasks + clear tags."""
from __future__ import annotations

import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.smart_verify import run_smart_verify_pipeline
from src.pipeline.smart_verify_common import clear_stale_verify_flags
from scripts.run_smart_verify import persist_result

log = logging.getLogger("fix_g7_tail")
logging.basicConfig(level=logging.INFO, format="%(message)s")

STUCK_TEXT: dict[str, dict] = {
    "G7_TB_27_639.1": {
        "answer": "при x = -8 значение равно 200, при x = 10 значение равно -250",
    },
    "G7_TB_33_863.1": {
        "answer": "при x = 15 равно 100, при x = -5 равно 100",
    },
    "G7_TB_33_863.2": {
        "answer": "при x = 14 равно 1, при x = -7 равно 400",
    },
}


def _tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(raw or "{}")


def main() -> int:
    engine = create_engine(get_settings().database_url)
    for tid, spec in STUCK_TEXT.items():
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT question_text, correct_answer, answer_type,
                           distractor_meta, tags
                    FROM tasks_master WHERE id = :id
                """),
                {"id": tid},
            ).mappings().first()
        if not row:
            log.warning("MISSING %s", tid)
            continue
        row = dict(row)
        answer = spec.get("answer", row["correct_answer"])
        tags = _tags(row["tags"])
        for key in (
            "fix_g7_reprocess_failed",
            "fix_g7_reprocess_failed2",
            "smart_verify_retry_exhausted",
            "smart_verify_retry_count",
            "smart_verify_error",
        ):
            tags.pop(key, None)
        clear_stale_verify_flags(tags)
        dmeta = row["distractor_meta"]
        if isinstance(dmeta, str):
            dmeta = json.loads(dmeta or "[]")
        log.info("VERIFY %s → %s", tid, answer[:70])
        result = run_smart_verify_pipeline(
            task_id=tid,
            question=row["question_text"],
            correct_answer=answer,
            answer_type="text",
            distractor_meta=dmeta,
            tags=tags,
        )
        persist_result(engine, tid, result)
        log.info("  → %s", result.get("action"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
