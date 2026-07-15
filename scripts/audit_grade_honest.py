#!/usr/bin/env python3
"""Honest quality audit for any grade — math-confirmed vs LLM-judge vs unverified."""
from __future__ import annotations

import argparse
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from scripts.audit_g6_quality_honest import validate_any

MATH_ROUTES = frozenset({"math_textbook", "math_corrected", "audit_math_fix", "audit_computed"})
LLM_ROUTES = frozenset({"local_prose_soft", "arbiter_equivalent", "arbiter_textbook", "arbiter_llm"})
OLD_RISK = frozenset({"consensus_corrected"})


def audit_level(level: int) -> int:
    e = create_engine(get_settings().database_url)
    with e.connect() as c:
        total = c.scalar(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
            """),
            {"level": level},
        )
        total_v = c.scalar(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level AND tm.verification_status = 'verified'
            """),
            {"level": level},
        )
        human = c.scalar(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags->>'smart_verify_status' = 'needs_human_review'
            """),
            {"level": level},
        )
        failed = c.scalar(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags->>'smart_verify_status' LIKE 'failed%'
            """),
            {"level": level},
        )
        regen = c.scalar(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags->>'distractor_regen_pending' = 'true'
            """),
            {"level": level},
        )
        compound = c.scalar(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags->>'smart_verify_status' = 'needs_compound_split'
            """),
            {"level": level},
        )
        full_path = c.scalar(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level AND tm.verification_status = 'verified'
                  AND coalesce(tm.tags->>'fix_g7_failed','false') != 'true'
                  AND coalesce(tm.tags->>'fix_g8_failed','false') != 'true'
                  AND coalesce(tm.tags->>'fix_g6_reverified','false') != 'true'
                  AND tm.tags->>'fix_g6_human_triage' IS NULL
                  AND tm.tags->>'fix_g6_final' IS NULL
                  AND coalesce(tm.tags->>'fix_g7_reprocessed','false') != 'true'
            """),
            {"level": level},
        )
        bypass_tag = f"fix_g{level}_failed"
        bypass_cnt = c.scalar(
            text(f"""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level AND tm.verification_status = 'verified'
                  AND tm.tags->>'{bypass_tag}' = 'true'
            """),
            {"level": level},
        ) or 0

        rows = c.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
                       coalesce(tm.tags->>'fix_g6_human_triage',
                                tm.tags->>'fix_g6_reverify_route',
                                tm.tags->>'fix_g6_final',
                                tm.tags->>'fix_g7_reprocessed',
                                '?') AS route
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level AND tm.verification_status = 'verified'
                  AND (tm.tags->>'fix_g6_reverified' = 'true'
                       OR tm.tags->>'fix_g6_human_triage' IS NOT NULL
                       OR tm.tags->>'fix_g6_final' IS NOT NULL
                       OR tm.tags->>'fix_g7_failed' = 'true'
                       OR tm.tags->>'fix_g7_reprocessed' = 'true'
                       OR tm.tags->>'fix_g8_failed' = 'true')
            """),
            {"level": level},
        ).mappings().all()

        sv_dist = c.execute(
            text("""
                SELECT coalesce(tags->>'smart_verify_status','pending') AS st, count(*) AS n
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                GROUP BY 1 ORDER BY n DESC LIMIT 12
            """),
            {"level": level},
        ).fetchall()

    stats = {"MATH_OK": 0, "MATH_FAIL": 0, "UNVERIFIED": 0}
    fails: list[tuple] = []
    for r in rows:
        v = validate_any(r["question_text"], r["correct_answer"], r["answer_type"] or "text")
        stats[v] += 1
        if v == "MATH_FAIL":
            fails.append((r["id"], r["route"], (r["correct_answer"] or "")[:40]))

    print("=" * 60)
    print(f"G{level} HONEST QUALITY AUDIT")
    print("=" * 60)
    print(f"Total tasks:                 {total}")
    print(f"Verified:                    {total_v} ({100*total_v/total:.1f}%)" if total else "")
    print(f"Full-path Smart Verify:      {full_path}")
    print(f"Bypass/fix-script verified:  {bypass_cnt}")
    print(f"Human_review:                {human}")
    print(f"Failed:                      {failed}")
    print(f"Compound split pending:      {compound}")
    print(f"Regen pending:               {regen}")
    print()
    print("--- smart_verify_status (top) ---")
    for st, n in sv_dist:
        print(f"  {st:30s} {n}")
    if rows:
        print()
        print("--- Bypass/fix-script answer validation ---")
        print(f"  MATH_OK:       {stats['MATH_OK']}")
        print(f"  MATH_FAIL:     {stats['MATH_FAIL']}")
        print(f"  UNVERIFIED:    {stats['UNVERIFIED']}")
        if fails:
            print()
            print("--- MATH_FAIL sample ---")
            for f in fails[:10]:
                print(f"  {f[0]} [{f[1]}] {f[2]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, required=True)
    args = ap.parse_args()
    return audit_level(args.level)


if __name__ == "__main__":
    raise SystemExit(main())
