#!/usr/bin/env python3
"""
Full-scan sympy adjudication for a grade — dump EVERY verified task whose
answer sympy marks False (candidate real error). No sampling.

Only computable answer types are checked; symbolic/prose types that sympy
cannot parse are reported separately as 'unknown' (not failures).
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy import try_validate_answer_for_question, try_validate_expression_answer
from src.pipeline.answer_sympy_gate import _try_validate_equation_answer

_COMPUTABLE = frozenset({
    "expression", "equation_solution", "exact_number", "fraction", "decimal",
    "inequality", "set",
})


def validate_row(q: str, ans: str, at: str) -> str:
    at = (at or "").lower()
    if not ans:
        return "no_answer"
    try:
        if at == "expression":
            v = try_validate_expression_answer(q, ans)
        elif at == "equation_solution":
            v = _try_validate_equation_answer(q, ans)
        elif at in ("exact_number", "fraction", "decimal", "inequality", "set"):
            v = try_validate_answer_for_question(q, ans, at)
        else:
            return "skip_type"
    except Exception:
        return "unknown"
    if v is True:
        return "ok"
    if v is False:
        return "fail"
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    e = create_engine(get_settings().database_url)
    with e.connect() as c:
        rows = c.execute(
            text(
                """
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :l AND tm.verification_status = 'verified'
                  AND tm.answer_type = ANY(:types)
                """
            ),
            {"l": args.level, "types": list(_COMPUTABLE)},
        ).mappings().all()

    counts = {"ok": 0, "fail": 0, "unknown": 0, "no_answer": 0, "skip_type": 0}
    fails = []
    for r in rows:
        res = validate_row(r["question_text"], r["correct_answer"], r["answer_type"])
        counts[res] += 1
        if res == "fail":
            tags = r["tags"] or {}
            fails.append({
                "id": r["id"],
                "q": r["question_text"],
                "a": r["correct_answer"],
                "type": r["answer_type"],
                "canon": tags.get("answer_canonical_source"),
                "sv": tags.get("smart_verify_status"),
                "prev": tags.get("answer_previous"),
            })

    print(f"G{args.level} computable={len(rows)} "
          f"ok={counts['ok']} FAIL={counts['fail']} unknown={counts['unknown']}")
    payload = json.dumps({"level": args.level, "fails": fails}, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(payload)
        print(f"wrote {len(fails)} fails -> {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
