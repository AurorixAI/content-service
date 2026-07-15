#!/usr/bin/env python3
"""Spot-check numeric answers among G5 failed_at_llm tasks."""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from src.core.config import get_settings
from src.pipeline.answer_sympy import try_validate_expression_answer

# Hand-computed corrections (textbook/OCR errors).
MANUAL_EXPECTED: dict[str, str] = {
    "G5_TB_18_335.1": "1036",
    "G5_TB_18_335.4": "9959",
}


def _eval_russian_expr(expr: str) -> int | None:
    s = expr.strip()
    s = s.replace(" ", "").replace(",", ".")
    s = s.replace(":", "/")
    s = re.sub(r"(\d)\.(\d)", r"\1.\2", s)
    # only safe arithmetic
    if not re.fullmatch(r"[\d+\-*/().]+", s):
        return None
    try:
        return int(eval(s, {"__builtins__": {}}))
    except Exception:
        return None


def main() -> None:
    e = create_engine(get_settings().database_url)
    with e.connect() as c:
        rows = c.execute(
            text("""
                SELECT tm.id, tm.correct_answer, tm.question_text
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 5
                  AND tm.tags->>'smart_verify_status' = 'failed_at_llm'
                ORDER BY tm.id
            """)
        ).fetchall()

    issues: list[tuple[str, str, str]] = []
    for r in rows:
        tid = r.id
        a = (r.correct_answer or "").strip()
        q = r.question_text or ""
        if tid in MANUAL_EXPECTED:
            exp = MANUAL_EXPECTED[tid]
            if a.replace(" ", "") != exp:
                issues.append((tid, a, f"manual_fix→{exp}"))
            continue
        if try_validate_expression_answer(q, a) is True:
            continue
        m = re.search(
            r"Найдите значение выражения\s*\n?(.+)",
            q,
            re.S | re.I,
        )
        if m and re.fullmatch(r"[\d,; ]+", a.replace(" ", "")):
            expr = m.group(1).strip()
            val = _eval_russian_expr(expr)
            if val is not None:
                nums = [x.strip().replace(" ", "") for x in a.split(",")]
                if len(nums) == 1 and nums[0].replace(".", "").isdigit():
                    stored = int(float(nums[0].replace(",", ".")))
                    if stored != val:
                        issues.append((tid, a, f"eval {expr} → {val}"))

    print(f"issues: {len(issues)}")
    for i in issues:
        print(i)


if __name__ == "__main__":
    main()
