#!/usr/bin/env python3
"""Sympy spot-check for G7/G8 verified non-text tasks."""
from __future__ import annotations

import argparse
import random
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy import try_validate_answer_for_question, try_validate_expression_answer
from src.pipeline.answer_sympy_gate import _try_validate_equation_answer


def validate_row(q: str, ans: str, at: str) -> str:
    at = (at or "").lower()
    if not ans:
        return "no_answer"
    if at == "expression":
        v = try_validate_expression_answer(q, ans)
    elif at == "equation_solution":
        v = _try_validate_equation_answer(q, ans)
    elif at in ("exact_number", "fraction", "decimal", "inequality", "set"):
        v = try_validate_answer_for_question(q, ans, at)
    else:
        return "skip"
    if v is True:
        return "ok"
    if v is False:
        return "fail"
    return "unknown"


def sample_stats(pool: list, n: int = 120) -> tuple[dict, list, int]:
    s = random.sample(pool, min(n, len(pool)))
    c: dict[str, int] = {"ok": 0, "fail": 0, "unknown": 0, "skip": 0}
    fails: list[tuple] = []
    for r in s:
        res = validate_row(r["question_text"], r["correct_answer"], r["answer_type"])
        c[res] += 1
        if res == "fail":
            fails.append((r["id"], (r["correct_answer"] or "")[:40]))
    return c, fails, len(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, required=True)
    args = ap.parse_args()
    level = args.level

    e = create_engine(get_settings().database_url)
    with e.connect() as c:
        buckets = c.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE coalesce(tags->>'fix_g7_reprocessed','false')='true') AS g7_reproc,
                  count(*) FILTER (WHERE coalesce(tags->>'fix_g8_failed','false')='true') AS g8_fix,
                  count(*) FILTER (WHERE coalesce(tags->>'answer_canonical_source','')='local_sympy') AS canon_local,
                  count(*) FILTER (WHERE coalesce(tags->>'answer_canonical_source','')='llm_fallback') AS canon_llm,
                  count(*) FILTER (WHERE verification_status='verified') AS verified,
                  count(*) FILTER (WHERE tags->>'distractor_regen_pending'='true') AS regen_pending
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :l
                """
            ),
            {"l": level},
        ).mappings().one()
        rows = c.execute(
            text(
                """
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :l AND tm.verification_status = 'verified'
                  AND tm.answer_type NOT IN ('text','open_text','coordinate','multiple_choice')
                """
            ),
            {"l": level},
        ).mappings().all()

    full = [r for r in rows if (r["tags"] or {}).get("fix_g7_reprocessed") != "true"]
    reproc = [r for r in rows if (r["tags"] or {}).get("fix_g7_reprocessed") == "true"]
    cf, ff, nf = sample_stats(full)
    cr, fr, nr = sample_stats(reproc) if reproc else ({}, [], 0)

    print("=" * 60)
    print(f"G{level} SYMPY SPOT CHECK (non-text verified)")
    print(f"  verified={buckets['verified']}  g7_reprocessed={buckets['g7_reproc']}  g8_fix={buckets['g8_fix']}")
    print(f"  canon_local={buckets['canon_local']}  canon_llm={buckets['canon_llm']}  regen_pending={buckets['regen_pending']}")
    print(f"  full-path pool={len(full)} sample={nf}: ok={cf['ok']} fail={cf['fail']} unk={cf['unknown']}")
    if ff:
        print("    fails:", ff[:5])
    if reproc:
        print(f"  reprocessed pool={len(reproc)} sample={nr}: ok={cr['ok']} fail={cr['fail']} unk={cr['unknown']}")
        if fr:
            print("    fails:", fr[:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
