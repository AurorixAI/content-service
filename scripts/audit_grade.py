#!/usr/bin/env python3
"""Full audit of failed tasks and distractor gaps for a grade."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text


def trunc(s: str | None, n: int = 80) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def classify_sympy_error(err: str) -> str:
    if not err:
        return "no_error_tag"
    if err == "gemini_code_execution_failed":
        return "llm_api_fail"
    if err == "empty absolute_correct_answer":
        return "llm_empty_answer"
    if err.startswith("local_mismatch"):
        return "local_mismatch"
    if err == "eval_failed":
        return "eval_failed"
    if "undecidable" in err:
        return "undecidable"
    if err.startswith("equation"):
        return "equation"
    if "multipart" in err or "compound" in err:
        return "compound"
    return "other_sympy"


def classify_distractor_gap(tags: dict, dist: int) -> str:
    err = tags.get("smart_verify_error") or ""
    sv = tags.get("smart_verify_status", "")
    passed = tags.get("distractor_gate_passed")
    rejected = tags.get("distractor_gate_rejected") or []
    regen = tags.get("distractor_regen_pending")

    if sv.startswith("failed"):
        return "verify_failed_not_dist"
    if err in ("gemini_code_execution_failed", "empty absolute_correct_answer"):
        if sv in ("verified_match", "verified_corrected", "generated_from_scratch"):
            return "stale_verify_error"
        return "verify_llm_fail"
    if err.startswith("local_mismatch") or err == "eval_failed":
        if sv in ("verified_match", "verified_corrected"):
            return "stale_sympy_error"
        return "verify_sympy_fail"
    if passed is not None:
        if passed == 0 and rejected:
            reasons = Counter(r.get("reason", "?") for r in rejected if isinstance(r, dict))
            top = reasons.most_common(1)
            return f"gate_all_rejected:{top[0][0]}" if top else "gate_all_rejected"
        if passed and passed < 3:
            return f"gate_partial:{passed}/3"
    if regen and dist == 0:
        return "regen_pending_no_gate_info"
    if dist == 0 and sv in ("verified_match", "verified_corrected"):
        return "verified_no_dist_unknown"
    return "other"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int, default=8)
    args = ap.parse_args()
    level = args.class_level

    engine = create_engine(os.environ.get("DATABASE_URL") or __import__(
        "src.core.config", fromlist=["get_settings"]
    ).get_settings().database_url)

    with engine.connect() as conn:
        failed = conn.execute(
            text("""
                SELECT tm.id, tm.answer_type, tm.question_text, tm.correct_answer,
                       tm.distractor_meta, tm.tags, tm.updated_at
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags->>'smart_verify_status' IN ('failed_at_llm', 'failed_at_sympy')
                ORDER BY tm.answer_type, tm.id
            """),
            {"level": level},
        ).fetchall()

        dist_gaps = conn.execute(
            text("""
                SELECT tm.id, tm.answer_type, tm.question_text, tm.correct_answer,
                       tm.distractor_meta, tm.tags, tm.updated_at
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags->>'smart_verify_status' IN (
                    'verified_match', 'verified_corrected', 'generated_from_scratch'
                  )
                  AND jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) < 3
                  AND tm.answer_type NOT IN ('text', 'open_text', 'coordinate')
                ORDER BY tm.answer_type, tm.id
            """),
            {"level": level},
        ).fetchall()

        human = conn.execute(
            text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags->>'smart_verify_status' = 'needs_human_review'
            """),
            {"level": level},
        ).scalar()

        total = conn.execute(
            text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
            """),
            {"level": level},
        ).scalar()

    print("=" * 72)
    print(f"G{level} TOTAL: {total}  |  failed: {len(failed)}  |  dist_gaps: {len(dist_gaps)}  |  human_review: {human}")
    print("=" * 72)

    # --- FAILED SUMMARY ---
    failed_by_status = Counter()
    failed_by_type = Counter()
    failed_by_class = Counter()
    for r in failed:
        tags = r.tags or {}
        sv = tags.get("smart_verify_status", "?")
        err = tags.get("smart_verify_error", "")
        failed_by_status[sv] += 1
        failed_by_type[r.answer_type] += 1
        failed_by_class[classify_sympy_error(err)] += 1

    print("\n## FAILED SUMMARY")
    print("By status:", dict(failed_by_status))
    print("By answer_type:", dict(failed_by_type))
    print("By error class:", dict(failed_by_class))

    print("\n## FAILED — каждая задача")
    for r in failed:
        tags = r.tags or {}
        err = tags.get("smart_verify_error", "")
        sv = tags.get("smart_verify_status", "")
        cand = tags.get("answer_gemini_candidate", "")
        sympy = tags.get("sympy_compatible_string", "")
        computed = tags.get("sympy_gate_reason", "")
        dist = len(r.distractor_meta or [])
        print(f"\n--- {r.id} ---")
        print(f"  type={r.answer_type}  status={sv}  dist={dist}")
        print(f"  Q: {trunc(r.question_text, 120)}")
        print(f"  A: {trunc(r.correct_answer, 100)}")
        print(f"  error: {err}")
        if cand:
            print(f"  gemini_candidate: {trunc(cand, 100)}")
        if sympy:
            print(f"  sympy_string: {trunc(sympy, 100)}")
        if computed and computed != err:
            print(f"  gate_reason: {computed}")

    # --- DISTRACTOR GAPS SUMMARY ---
    gap_by_type = Counter()
    gap_by_cause = Counter()
    gap_details: list[dict] = []

    for r in dist_gaps:
        tags = r.tags or {}
        dist = len(r.distractor_meta or [])
        cause = classify_distractor_gap(tags, dist)
        gap_by_type[r.answer_type] += 1
        gap_by_cause[cause.split(":")[0]] += 1
        rejected = tags.get("distractor_gate_rejected") or []
        gap_details.append({
            "id": r.id,
            "type": r.answer_type,
            "cause": cause,
            "sv": tags.get("smart_verify_status"),
            "err": tags.get("smart_verify_error", ""),
            "passed": tags.get("distractor_gate_passed"),
            "rejected": rejected[:5],
            "Q": trunc(r.question_text, 100),
            "A": trunc(r.correct_answer, 80),
        })

    print("\n" + "=" * 72)
    print("## DISTRACTOR GAPS SUMMARY")
    print("By answer_type:", dict(gap_by_type))
    print("By root cause:", dict(gap_by_cause))

    print("\n## DISTRACTOR GAPS — каждая задача")
    for g in gap_details:
        print(f"\n--- {g['id']} ---")
        print(f"  type={g['type']}  status={g['sv']}  cause={g['cause']}")
        print(f"  Q: {g['Q']}")
        print(f"  A: {g['A']}")
        if g["err"]:
            print(f"  smart_verify_error: {g['err'][:120]}")
        if g["passed"] is not None:
            print(f"  distractor_gate_passed: {g['passed']}")
        if g["rejected"]:
            print("  gate_rejected (sample):")
            for rej in g["rejected"]:
                if isinstance(rej, dict):
                    print(f"    - {rej.get('value','?')[:40]} → {rej.get('reason','?')}")

    # --- ACTIONABLE GROUPS ---
    print("\n" + "=" * 72)
    print("## РЕКОМЕНДАЦИИ ПО ГРУППАМ")

    groups: dict[str, list[str]] = defaultdict(list)
    for r in failed:
        tags = r.tags or {}
        err = tags.get("smart_verify_error", "")
        cls = classify_sympy_error(err)
        if cls == "local_mismatch" and r.answer_type == "set":
            groups["fix_set_gate"].append(r.id)
        elif cls == "local_mismatch" and r.answer_type == "inequality":
            groups["fix_inequality_gate"].append(r.id)
        elif cls == "eval_failed" and r.answer_type == "expression":
            groups["ocr_wrong_answer_expression"].append(r.id)
        elif cls == "eval_failed":
            groups["eval_failed_other"].append(r.id)
        elif cls == "llm_api_fail":
            groups["retry_llm"].append(r.id)
        elif "undecidable" in err:
            groups["undecidable"].append(r.id)
        else:
            groups[f"failed_{cls}"].append(r.id)

    for g in dist_gaps:
        tags = g.tags or {}
        cause = classify_distractor_gap(tags, len(g.distractor_meta or []))
        if cause.startswith("stale"):
            groups["dist_stale_error_clear_and_retry"].append(g.id)
        elif cause.startswith("gate_all_rejected"):
            groups["dist_gate_rejects_all"].append(g.id)
        elif cause == "regen_pending_no_gate_info":
            groups["dist_llm_silent_fail"].append(g.id)
        else:
            groups[f"dist_{cause.split(':')[0]}"].append(g.id)

    for name, ids in sorted(groups.items()):
        print(f"\n{name} ({len(ids)}):")
        for tid in ids:
            print(f"  {tid}")


if __name__ == "__main__":
    main()
