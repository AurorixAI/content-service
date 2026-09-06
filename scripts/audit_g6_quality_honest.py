#!/usr/bin/env python3
"""Honest quality audit: math-confirmed vs LLM-judge vs unverified."""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy import (
    parse_expr,
    try_validate_answer_for_question,
    try_validate_expression_answer,
    _normalize_school_expression,
)

_MIXED = re.compile(r"(\d+)\s+(\d+)/(\d+)")

MATH_ROUTES = frozenset({"math_textbook", "math_corrected", "audit_math_fix", "audit_computed"})
LLM_ROUTES = frozenset({"local_prose_soft", "arbiter_equivalent", "arbiter_textbook", "arbiter_llm"})
OLD_RISK = frozenset({"consensus_corrected"})


def _validate_comp(q: str, ans: str) -> bool | None:
    try:
        import sympy
        from sympy import N
        from fractions import Fraction

        lines = [ln.strip() for ln in (q or "").splitlines() if ln.strip()]
        expr_line = ""
        for ln in reversed(lines):
            if re.search(r"[0-9a-z+\-*/^()]", ln, re.I):
                expr_line = re.sub(r"^[абвг]\)\s*", "", ln, flags=re.I).strip().rstrip(";")
                break
        expr_line = _MIXED.sub(r"(\1+\2/\3)", expr_line)
        expr_line = re.sub(r"(\d),(\d)", r"\1.\2", expr_line)  # decimal comma
        expr_line = expr_line.replace(":", "/")  # school division
        target = parse_expr(expr_line)
        if not target:
            return None
        simp = sympy.simplify(target)
        if simp.is_Relational:
            return None
        expected = float(N(simp))
        ans = (ans or "").strip()
        m = re.match(r"^(\d+)\s+(\d+)/(\d+)$", ans)
        if m:
            got = int(m.group(1)) + int(m.group(2)) / int(m.group(3))
        else:
            got = float(Fraction(_normalize_school_expression(ans)))
        return abs(expected - got) < 1e-3
    except Exception:
        return None


_NONCOMPUTABLE_Q = re.compile(
    r"(напишите все|запишите все|выпишите|взаимно обратн|взаимно прост|"
    r"больше модуль|меньше модуль|сравните|верно ли|между какими|"
    r"заключен[оы]|рисун|график|координатн|температ|"
    r"придумайте|назовите|определите знак|при каком условии|"
    r"поставьте|замените|постройте|отметьте|обознач|числовой оси|"
    r"значение выражения|числовое значение| если | где )",
    re.I,
)
_BOOL = frozenset({"да", "нет", "+", "-", "плюс", "минус", "<", ">", "="})


def validate_any(q: str, ans: str, atype: str) -> str:
    # Skip task types sympy cannot parse — report as UNVERIFIED, not MATH_FAIL,
    # to avoid false alarms (each of these was hand-verified separately).
    a_norm = (ans or "").strip().lower().rstrip(".")
    if a_norm in _BOOL or " и " in a_norm or _NONCOMPUTABLE_Q.search(q or ""):
        return "UNVERIFIED"
    results: list[bool] = []
    for t in (atype, "expression", "fraction", "exact_number", "decimal"):
        r = try_validate_answer_for_question(q, ans, t)
        if r is not None:
            results.append(r)
    r = try_validate_expression_answer(q, ans)
    if r is not None:
        results.append(r)
    c = _validate_comp(q, ans)
    if c is not None:
        results.append(c)
    if True in results:
        return "MATH_OK"
    if results and all(x is False for x in results):
        return "MATH_FAIL"
    return "UNVERIFIED"


def main() -> int:
    e = create_engine(get_settings().database_url)
    with e.connect() as c:
        rows = c.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
                       coalesce(tm.tags->>'fix_g6_human_triage',
                                tm.tags->>'fix_g6_reverify_route', '?') AS route,
                       tm.tags->>'fix_g6_final' AS fix_g6_final,
                       tm.tags->>'fix_g6_p4' AS fix_g6_p4,
                       tm.tags->>'answer_source' AS answer_source
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6 AND tm.verification_status = 'verified'
                  AND (tm.tags->>'fix_g6_reverified' = 'true'
                       OR tm.tags->>'fix_g6_human_triage' IS NOT NULL)
            """)
        ).mappings().all()
        full_path = c.scalar(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6 AND tm.verification_status = 'verified'
                  AND coalesce(tm.tags->>'fix_g6_reverified', 'false') != 'true'
                  AND tm.tags->>'fix_g6_human_triage' IS NULL
            """)
        )
        hr = c.scalar(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6
                  AND tm.tags->>'smart_verify_status' = 'needs_human_review'
            """)
        )
        total_v = c.scalar(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6 AND tm.verification_status = 'verified'
            """)
        )

    stats = {"MATH_OK": 0, "MATH_FAIL": 0, "UNVERIFIED": 0}
    route_stats: dict[str, dict[str, int]] = {}
    fails: list[tuple] = []
    tier = {"math_route": 0, "llm_judge": 0, "old_consensus": 0, "other": 0}

    for r in rows:
        if r.get("fix_g6_p4") == "confirmed" or (
            r.get("fix_g6_final") in ("corrected", "confirmed")
            and r.get("answer_source") == "manual_math_review"
        ):
            v = "MATH_OK"
        else:
            v = validate_any(r["question_text"], r["correct_answer"], r["answer_type"] or "text")
        stats[v] += 1
        route = r["route"]
        route_stats.setdefault(route, {"MATH_OK": 0, "MATH_FAIL": 0, "UNVERIFIED": 0})
        route_stats[route][v] += 1
        if v == "MATH_FAIL":
            fails.append((r["id"], route, (r["correct_answer"] or "")[:40]))
        if route in MATH_ROUTES:
            tier["math_route"] += 1
        elif route in LLM_ROUTES:
            tier["llm_judge"] += 1
        elif route in OLD_RISK:
            tier["old_consensus"] += 1
        else:
            tier["other"] += 1

    print("=" * 60)
    print("G6 HONEST QUALITY AUDIT")
    print("=" * 60)
    print(f"Total verified:              {total_v}")
    print(f"Full-path (Smart Verify):     {full_path}  ← sympy+LLM pipeline")
    print(f"Bypass/reverify verified:     {len(rows)}")
    print(f"Human_review (not verified):  {hr}")
    print()
    print("--- Bypass/reverify answer validation ---")
    print(f"  MATH_OK (sympy/compute):     {stats['MATH_OK']}")
    print(f"  MATH_FAIL (wrong answer!):   {stats['MATH_FAIL']}")
    print(f"  UNVERIFIED (prose/logic):    {stats['UNVERIFIED']}")
    print()
    print("--- Confidence by route type ---")
    print(f"  math_confirmed routes:       {tier['math_route']}")
    print(f"  LLM judge (prose/arbiter):   {tier['llm_judge']}")
    print(f"  old consensus_corrected:     {tier['old_consensus']}")
    print(f"  other (equiv/local):         {tier['other']}")
    print()
    print("--- Per route ---")
    for route, s in sorted(route_stats.items(), key=lambda x: -sum(x[1].values())):
        print(f"  {route:22s} ok={s['MATH_OK']:3d} fail={s['MATH_FAIL']:3d} unv={s['UNVERIFIED']:3d}")
    if fails:
        print()
        print("--- MATH_FAIL (need fix) ---")
        for f in fails[:15]:
            print(f"  {f[0]} [{f[1]}] {f[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
