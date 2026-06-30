#!/usr/bin/env python3
"""
Revert blind Gemini corrections (before SymPy gate / dual consensus).

Restores answer_previous, clears distractors generated on wrong answer,
resets verify tags so audit re-processes with new logic.

Usage:
  docker exec content-worker python /app/scripts/revert_blind_corrections.py --dry-run
  docker exec content-worker python /app/scripts/revert_blind_corrections.py --class-level 8
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("revert_blind")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy import sympy_equivalent, try_validate_answer_for_question


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--class-level", type=int, default=8)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    engine = create_engine(get_settings().database_url)
    sql = text("""
        SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = :grade
          AND COALESCE(tm.tags->>'answer_corrected_by_gemini', 'false') = 'true'
          AND COALESCE(tm.tags->>'answer_corrected_sympy_confirmed', 'false') != 'true'
          AND COALESCE(tm.tags->>'answer_corrected_dual_consensus', 'false') != 'true'
        ORDER BY tm.id
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"grade": args.class_level}).fetchall()

    log.info("Blind corrections to review: %d", len(rows))
    reverted = kept = 0

    for tid, question, current, atype, tags_raw in rows:
        tags = tags_raw if isinstance(tags_raw, dict) else json.loads(tags_raw or "{}")
        prev = (tags.get("answer_previous") or "").strip()
        if not prev:
            kept += 1
            continue

        should_revert = True
        prev_ok = try_validate_answer_for_question(question or "", prev, atype or "")
        cur_ok = try_validate_answer_for_question(question or "", current or "", atype or "")
        try:
            sym = sympy_equivalent(prev, current or "", atype or "")
        except Exception as exc:
            log.warning("  %s sympy compare error: %s", tid, exc)
            sym = None

        if sym is True:
            reason = "sympy_equivalent"
        elif prev_ok is True and cur_ok is not True:
            reason = "stored_was_valid"
        elif prev_ok is True and cur_ok is False:
            reason = "gemini_broke_valid"
        else:
            reason = "blind_correction"

        if should_revert:
            log.info("  ↩ %s [%s] %r → %r", tid, reason, (current or "")[:40], prev[:40])
            if not args.dry_run:
                new_tags = dict(tags)
                for k in (
                    "answer_corrected_by_gemini", "answer_corrected_sympy_confirmed",
                    "answer_corrected_dual_consensus", "answer_previous",
                    "answer_gemini_verified", "answer_verify_mode",
                    "answer_gemini_candidate", "distractor_regen_pending",
                    "distractors_cleared_for_correction",
                ):
                    new_tags.pop(k, None)
                new_tags["verify_reverted"] = True
                new_tags["verify_revert_reason"] = reason
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE tasks_master
                            SET correct_answer = :ans,
                                tags = cast(:tags as jsonb),
                                distractor_meta = '[]'::jsonb
                            WHERE id = :id
                        """),
                        {
                            "id": tid,
                            "ans": prev,
                            "tags": json.dumps(new_tags, ensure_ascii=False),
                        },
                    )
            reverted += 1
        else:
            kept += 1

    log.info("Done: reverted=%d kept=%d dry_run=%s", reverted, kept, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
