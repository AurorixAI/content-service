#!/usr/bin/env python3
"""G7 verification quality audit — how tasks were verified."""
from __future__ import annotations

import json
import random
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy import try_validate_answer_for_question, try_validate_expression_answer
from src.pipeline.answer_sympy_gate import _try_validate_equation_answer
from src.pipeline.distractor_gate import stored_distractors_valid


def main() -> int:
    engine = create_engine(get_settings().database_url)
    level = 7

    with engine.connect() as conn:
        summary = conn.execute(
            text("""
                SELECT
                  count(*) AS total,
                  count(*) FILTER (WHERE verification_status = 'verified') AS verified,
                  count(*) FILTER (WHERE tags->>'fix_g7_failed' = 'true') AS fix_script,
                  count(*) FILTER (WHERE verification_status = 'verified'
                    AND coalesce(tags->>'fix_g7_failed','false') != 'true') AS full_path_verified,
                  count(*) FILTER (WHERE tags->>'smart_verify_status' = 'verified_match') AS verified_match,
                  count(*) FILTER (WHERE tags->>'smart_verify_status' = 'verified_corrected') AS verified_corrected,
                  count(*) FILTER (WHERE tags->>'smart_verify_status' = 'generated_from_scratch') AS from_scratch,
                  count(*) FILTER (WHERE tags->>'smart_verify_status' = 'needs_human_review') AS human_review,
                  count(*) FILTER (WHERE tags->>'smart_verify_status' = 'needs_compound_split') AS compound_split,
                  count(*) FILTER (WHERE tags->>'answer_canonical_source' = 'local_sympy') AS canon_local,
                  count(*) FILTER (WHERE tags->>'answer_canonical_source' = 'llm_fallback') AS canon_llm,
                  count(*) FILTER (WHERE tags->>'answer_canonical_source' = 'equation_solved') AS canon_eq
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
            """),
            {"level": level},
        ).mappings().one()

        rows = conn.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
                       tm.distractor_meta, tm.tags, tm.verification_status
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
            """),
            {"level": level},
        ).mappings().all()

    print("=" * 60)
    print("G7 VERIFICATION QUALITY AUDIT")
    print("=" * 60)
    for k, v in summary.items():
        print(f"  {k:22} {v}")

    # Distractor quality on verified non-text
    dist_ok = dist_missing = dist_bad = 0
    fix_dist_ok = fix_dist_bad = 0
    validate_ok = validate_fail = validate_unknown = 0
    fix_validate_ok = fix_validate_fail = fix_validate_unknown = 0

    fix_rows = [r for r in rows if (r["tags"] or {}).get("fix_g7_failed") == "true"]
    sample_fix = random.sample(fix_rows, min(80, len(fix_rows)))

    def validate_row(row) -> str:
        q = row["question_text"] or ""
        ans = (row["correct_answer"] or "").strip()
        at = (row["answer_type"] or "").lower()
        if not ans:
            return "no_answer"
        if at == "expression":
            v = try_validate_expression_answer(q, ans)
        elif at == "equation_solution":
            v = _try_validate_equation_answer(q, ans)
        elif at in ("exact_number", "fraction", "decimal", "inequality", "set"):
            v = try_validate_answer_for_question(q, ans, at)
        else:
            return "skip_type"
        if v is True:
            return "ok"
        if v is False:
            return "fail"
        return "unknown"

    for row in rows:
        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        if row["verification_status"] != "verified":
            continue
        at = (row["answer_type"] or "").lower()
        if at in ("text", "open_text", "coordinate"):
            continue
        dmeta = row["distractor_meta"] if isinstance(row["distractor_meta"], list) else json.loads(row["distractor_meta"] or "[]")
        if len(dmeta) < 2:
            dist_missing += 1
            continue
        valid = stored_distractors_valid(
            dmeta,
            question=row["question_text"] or "",
            correct_answer=row["correct_answer"] or "",
            answer_type=row["answer_type"] or "",
            min_count=2,
        )
        if valid:
            dist_ok += 1
            if tags.get("fix_g7_failed") == "true":
                fix_dist_ok += 1
        else:
            dist_bad += 1
            if tags.get("fix_g7_failed") == "true":
                fix_dist_bad += 1

    for row in sample_fix:
        res = validate_row(row)
        if res == "ok":
            fix_validate_ok += 1
        elif res == "fail":
            fix_validate_fail += 1
        elif res != "skip_type":
            fix_validate_unknown += 1

    print("\n--- Verified non-text distractors ---")
    print(f"  gate_ok:      {dist_ok}")
    print(f"  missing(<2):  {dist_missing}")
    print(f"  gate_failed:  {dist_bad}")

    print("\n--- fix_g7_failed sample validation (sympy) ---")
    print(f"  sample_size:  {len(sample_fix)}")
    print(f"  sympy_ok:     {fix_validate_ok}")
    print(f"  sympy_fail:   {fix_validate_fail}")
    print(f"  sympy_unknown:{fix_validate_unknown}")

    not_verified = [r for r in rows if r["verification_status"] != "verified"]
    print(f"\n--- Not verified: {len(not_verified)} ---")
    from collections import Counter
    c = Counter(
        (r["tags"] if isinstance(r["tags"], dict) else json.loads(r["tags"] or "{}")).get("smart_verify_status", "?")
        for r in not_verified
    )
    for k, v in c.most_common():
        print(f"  {k}: {v}")

    pct_full = 100 * summary["full_path_verified"] / summary["verified"] if summary["verified"] else 0
    print(f"\n--- QUALITY SCORE ---")
    print(f"  Full smart-verify path: {summary['full_path_verified']}/{summary['verified']} ({pct_full:.1f}%)")
    print(f"  fix_g7_failed bypass:   {summary['fix_script']} tasks")
    print(f"  Needs human review:     {summary['human_review']}")
    print(f"  Needs compound split:   {summary['compound_split']}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
