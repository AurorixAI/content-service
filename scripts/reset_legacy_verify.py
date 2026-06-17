#!/usr/bin/env python3
"""Reset pre-SymPy verify tags so tasks re-enter the max-quality audit queue."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("reset_legacy_verify")

from sqlalchemy import create_engine, text

from src.core.config import get_settings

_LEGACY_MODES = ("match", "corrected", "corrected_dual", "")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--class-level", type=int, default=8)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    engine = create_engine(get_settings().database_url)
    sql = text("""
        SELECT tm.id, tm.tags
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = :grade
          AND COALESCE(tm.tags->>'answer_gemini_verified', 'false') = 'true'
          AND (
            tm.tags->>'answer_verify_mode' IS NULL
            OR tm.tags->>'answer_verify_mode' IN ('match', 'corrected', 'corrected_dual')
            OR COALESCE(tm.tags->>'verify_reverted', 'false') = 'true'
          )
        ORDER BY tm.id
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"grade": args.class_level}).fetchall()

    log.info("Legacy verify tags to reset (class %d): %d", args.class_level, len(rows))
    if args.dry_run:
        return 0

    strip_keys = (
        "answer_gemini_verified",
        "answer_verify_mode",
        "answer_corrected_by_gemini",
        "answer_corrected_sympy_confirmed",
        "answer_corrected_dual_consensus",
        "verify_reverted",
        "answer_gemini_candidate",
        "answer_gemini_flash",
    )

    updated = 0
    for tid, tags_raw in rows:
        tags = tags_raw if isinstance(tags_raw, dict) else json.loads(tags_raw or "{}")
        for k in strip_keys:
            tags.pop(k, None)
        tags["verify_reset_for_max_quality"] = True
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE tasks_master SET tags = cast(:tags as jsonb) WHERE id = :id"),
                {"id": tid, "tags": json.dumps(tags, ensure_ascii=False)},
            )
        updated += 1

    log.info("Reset %d tasks — they will re-enter verify+distractor queue", updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
