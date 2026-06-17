"""Точечное заполнение distractor_meta для задач с ответом но без дистракторов."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, "/app")

from src.core.config import get_settings
from src.pipeline.post_processing import _make_distractors

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fill_distractor_gaps")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="G6_", help="Task id prefix, e.g. G6_")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, question_text, correct_answer, answer_type
                FROM tasks_master
                WHERE id LIKE :prefix
                  AND (distractor_meta IS NULL OR distractor_meta = '[]'::jsonb)
                  AND correct_answer IS NOT NULL
                  AND correct_answer != ''
                  AND correct_answer NOT IN ('—', '-')
                ORDER BY id
            """),
            {"prefix": f"{args.prefix}%"},
        ).mappings().fetchall()

    log.info("Found %d tasks with answer but no distractors (prefix=%s)", len(rows), args.prefix)
    if not rows:
        return 0

    updated = 0
    for row in rows:
        tid = row["id"]
        q = row["question_text"] or ""
        ans = row["correct_answer"] or ""
        atype = row["answer_type"] or "exact_number"

        distractors, dmeta = _make_distractors(tid, q, ans, atype)
        if not dmeta:
            log.warning("  SKIP %s — Gemini returned empty", tid)
            continue

        log.info("  OK %s → %d distractors", tid, len(dmeta))
        if args.dry_run:
            updated += 1
            continue

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET distractor_meta = cast(:dmeta as jsonb)
                    WHERE id = :id
                """),
                {"id": tid, "dmeta": json.dumps(dmeta, ensure_ascii=False)},
            )
        updated += 1

    log.info("Done: %d / %d updated", updated, len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
