#!/usr/bin/env python3
"""Fix G8 TB group A: numeric compute tasks misclassified as expression."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.smart_verify_common import run_distractor_only_pipeline

log = logging.getLogger("fix_tb_group_a")
logging.basicConfig(level=logging.INFO, format="%(message)s")

GROUP_A = [
    "G8_TB_17_395.4.1",
    "G8_TB_17_395.4.2",
    "G8_TB_17_395.4.3",
    "G8_TB_17_395.4.4",
    "G8_TB_47_1176.4.1",
    "G8_TB_47_1176.4.2",
    "G8_TB_47_1176.4.3",
    "G8_TB_47_1176.4.4",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, question_text, correct_answer, answer_type, distractor_meta, tags
                FROM tasks_master
                WHERE id = ANY(:ids)
                ORDER BY id
            """),
            {"ids": GROUP_A},
        ).mappings().all()

    if len(rows) != len(GROUP_A):
        found = {r["id"] for r in rows}
        missing = set(GROUP_A) - found
        log.error("Missing tasks: %s", missing)
        return 1

    ok = fail = 0
    for row in rows:
        tid = row["id"]
        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        old_type = row["answer_type"]

        tags.pop("distractor_regen_exhausted", None)
        tags.pop("distractor_regen_attempts", None)
        tags.pop("distractor_regen_pending", None)
        tags.pop("choices_complete", None)
        tags.pop("distractor_count_partial", None)
        tags["smart_verify_status"] = "verified_match"
        tags["answer_verify_mode"] = "verified_match"

        log.info("%s: %s → exact_number | A=%s", tid, old_type, (row["correct_answer"] or "")[:40])

        if args.dry_run:
            continue

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET answer_type = 'exact_number',
                        tags = cast(:tags AS jsonb),
                        distractor_meta = '[]'::jsonb,
                        verification_status = 'verified'
                    WHERE id = :id
                """),
                {"id": tid, "tags": json.dumps(tags, ensure_ascii=False)},
            )

        result = run_distractor_only_pipeline(
            task_id=tid,
            question=row["question_text"] or "",
            correct_answer=row["correct_answer"] or "",
            answer_type="exact_number",
            distractor_meta=[],
            tags=tags,
        )

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET distractor_meta = cast(:dmeta AS jsonb),
                        tags = cast(:tags AS jsonb),
                        verification_status = :vstatus
                    WHERE id = :id
                """),
                {
                    "id": tid,
                    "dmeta": json.dumps(result["distractor_meta"] or [], ensure_ascii=False),
                    "tags": json.dumps(result["tags"], ensure_ascii=False),
                    "vstatus": result.get("verification_status", "verified"),
                },
            )

        dist_n = len(result["distractor_meta"] or [])
        exhausted = result["tags"].get("distractor_regen_exhausted")
        status = "OK" if dist_n >= 2 and not exhausted else "FAIL"
        log.info("  → %s dist=%d exhausted=%s action=%s", status, dist_n, exhausted, result.get("action"))
        if dist_n >= 2 and not exhausted:
            ok += 1
        else:
            fail += 1

    if args.dry_run:
        log.info("Dry-run: would fix %d tasks", len(rows))
    else:
        log.info("Done: ok=%d fail=%d", ok, fail)
    return 0 if fail == 0 or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
