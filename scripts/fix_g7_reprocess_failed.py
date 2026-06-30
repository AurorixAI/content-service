#!/usr/bin/env python3
"""
Repair 50 fix_g7_reprocess_failed tasks — manual answers + retry prep.

Usage:
  python scripts/fix_g7_reprocess_failed.py --dry-run
  python scripts/fix_g7_reprocess_failed.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.smart_verify_common import clear_stale_verify_flags

log = logging.getLogger("fix_g7_reprocess_failed")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Broken/truncated answers, wrong stored values, prose → text
MANUAL_ANSWER_FIXES: dict[str, dict] = {
    "G7_ALG_19_12": {"answer": "5"},
    "G7_ALG_33_4.1": {"answer": "(0; 2)", "answer_type": "multiple_choice"},
    "G7_ALG_33_4.3": {"answer": "(1; 2)", "answer_type": "multiple_choice"},
    "G7_TB_28_677.1": {"answer": "x = 0, x = -8"},
    "G7_TB_42_1072.1": {"answer": "нет"},
    "G7_TB_42_1072.2": {"answer": "да"},
    "G7_TB_43_1087.3": {"answer": "u = 13/3, v = -10/9"},
    "G7_TB_43_1087.4": {"answer": "p = 9/4, q = -7/2"},
    "G7_TB_43_1088.1": {"answer": "(0; -2,8)"},
    "G7_TB_43_1089.3": {"answer": "(-3,5; -3)"},
    "G7_TB_43_1090.2": {"answer": "(-0,84375; 6,8125)"},
    "G7_ALG_6_6.1": {"answer": "1,7 * 10^1"},
    "G7_ALG_9_9.4": {"answer": "2x^6y^3, -8192"},
    "G7_ALG_9_9.6": {"answer": "4a^4b^5, -1"},
    "G7_ALG_23_7.3": {
        "answer": "2t^3/(k^2t^3), kt^2/(12k^2t^3), 36k^2/(12k^2t^3)",
    },
    "G7_TB_27_638.1": {
        "answer": "при x = 3 значение равно 15, при x = -3 значение равно 33",
        "answer_type": "text",
    },
    "G7_TB_27_639.1": {
        "answer": "при x = -8 значение равно 200, при x = 1 значение равно 0",
        "answer_type": "text",
    },
    "G7_TB_33_863.1": {
        "answer": "при x = 15 равно 100, при x = -5 равно 0",
        "answer_type": "text",
    },
    "G7_TB_33_863.2": {
        "answer": "при x = 14 равно 1, при x = -7 равно 0",
        "answer_type": "text",
    },
    "G7_ALG_13_7": {
        "answer": "S_1 = (a + b)(c + d) = ac + ad + bc + bd; S_2 = x(y - z) + z(x - w)",
        "answer_type": "text",
    },
    "G7_ALG_34_1.3": {"answer": "x - 2y = 4"},
}


def _tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(raw or "{}")


def _clear_retry(tags: dict) -> None:
    for key in (
        "distractor_regen_exhausted",
        "distractor_regen_attempts",
        "distractor_regen_pending",
        "smart_verify_retry_exhausted",
        "smart_verify_retry_count",
        "smart_verify_error",
        "fix_g7_reprocess_failed2",
    ):
        tags.pop(key, None)


def fetch_reprocess_failed(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.correct_answer, tm.answer_type, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 7
                  AND tm.tags->>'fix_g7_reprocess_failed' = 'true'
                ORDER BY tm.id
            """),
        ).mappings().all()
    return [dict(r) for r in rows]


def apply_manual_fixes(engine, *, dry_run: bool) -> dict[str, int]:
    stats = {"fixed": 0, "skipped": 0, "missing": 0}
    with engine.begin() as conn:
        for tid, spec in MANUAL_ANSWER_FIXES.items():
            row = conn.execute(
                text("""
                    SELECT id, correct_answer, answer_type, tags
                    FROM tasks_master WHERE id = :id
                """),
                {"id": tid},
            ).mappings().first()
            if not row:
                log.warning("  MISSING %s", tid)
                stats["missing"] += 1
                continue
            row = dict(row)
            tags = _tags(row["tags"])
            if tags.get("fix_g7_reprocess_failed") != "true":
                stats["skipped"] += 1
                continue
            answer = spec.get("answer", row["correct_answer"])
            atype = spec.get("answer_type", row["answer_type"])
            log.info("  MANUAL %s → %s (%s)", tid, answer[:70], atype)
            if dry_run:
                stats["fixed"] += 1
                continue
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        answer_type = :atype,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": tid, "ans": answer, "atype": atype},
            )
            stats["fixed"] += 1
    return stats


def reset_for_reverify(engine, *, dry_run: bool) -> dict[str, int]:
    rows = fetch_reprocess_failed(engine)
    stats = {"reset": 0}
    if dry_run:
        log.info("Would reset %d tasks for Smart Verify reprocess", len(rows))
        return stats
    with engine.begin() as conn:
        for row in rows:
            tags = _tags(row["tags"])
            _clear_retry(tags)
            clear_stale_verify_flags(tags)
            tags["fix_g7_reprocess_failed"] = "true"
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET tags = cast(:tags AS jsonb),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": row["id"],
                    "tags": json.dumps(tags, ensure_ascii=False),
                },
            )
            stats["reset"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    rows = fetch_reprocess_failed(engine)
    log.info("fix_g7_reprocess_failed tasks: %d", len(rows))

    m = apply_manual_fixes(engine, dry_run=args.dry_run)
    log.info("Manual fixes: %s", m)

    r = reset_for_reverify(engine, dry_run=args.dry_run)
    log.info("Reset for reverify: %s", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
