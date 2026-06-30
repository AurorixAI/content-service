#!/usr/bin/env python3
"""Fix G8 TB group D: scientific notation → simple decimal for open input."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.smart_verify_common import run_distractor_only_pipeline

log = logging.getLogger("fix_tb_group_d")
logging.basicConfig(level=logging.INFO, format="%(message)s")

GROUP_D = ["G8_TB_48_1184.2"]

# Student types plain number; -2e-05 is hostile for open input.
CANONICAL_ANSWER = "-0.00002"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, question_text, correct_answer, answer_type, distractor_meta, tags
                FROM tasks_master WHERE id = ANY(:ids)
            """),
            {"ids": GROUP_D},
        ).mappings().first()

    if not row:
        log.error("Task not found")
        return 1

    tid = row["id"]
    tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
    log.info("%s: %s → exact_number | A: %s → %s", tid, row["answer_type"], row["correct_answer"], CANONICAL_ANSWER)

    if args.dry_run:
        return 0

    for key in (
        "distractor_regen_exhausted",
        "distractor_regen_attempts",
        "distractor_regen_pending",
        "choices_complete",
    ):
        tags.pop(key, None)
    tags["smart_verify_status"] = "verified_corrected"
    tags["answer_verify_mode"] = "verified_corrected"
    tags["answer_normalized"] = "scientific_to_decimal"

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tasks_master
                SET answer_type = 'exact_number',
                    correct_answer = :ans,
                    tags = cast(:tags AS jsonb),
                    distractor_meta = '[]'::jsonb,
                    verification_status = 'verified'
                WHERE id = :id
            """),
            {
                "id": tid,
                "ans": CANONICAL_ANSWER,
                "tags": json.dumps(tags, ensure_ascii=False),
            },
        )

    result = run_distractor_only_pipeline(
        task_id=tid,
        question=row["question_text"] or "",
        correct_answer=CANONICAL_ANSWER,
        answer_type="exact_number",
        distractor_meta=[],
        tags=tags,
    )

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tasks_master
                SET distractor_meta = cast(:dmeta AS jsonb),
                    tags = cast(:tags AS jsonb)
                WHERE id = :id
            """),
            {
                "id": tid,
                "dmeta": json.dumps(result["distractor_meta"] or [], ensure_ascii=False),
                "tags": json.dumps(result["tags"], ensure_ascii=False),
            },
        )

    dist_n = len(result["distractor_meta"] or [])
    log.info("  → dist=%d exhausted=%s", dist_n, result["tags"].get("distractor_regen_exhausted"))
    return 0 if dist_n >= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
