#!/usr/bin/env python3
"""Solve G7 coordinate systems from question text via SymPy."""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from sympy import Eq, Rational, symbols, solve

from src.core.config import get_settings


def _extract_system(question: str) -> list[tuple[str, str]] | None:
    q = question.replace("$", "")
    m = re.search(r"\\begin\{cases\}(.*?)\\end\{cases\}", q, re.S)
    if m:
        block = m.group(1)
        parts = re.split(r"\\\\", block)
    else:
        # plain: "eq1, eq2" or newline-separated
        tail = q.split("\n", 1)[-1]
        parts = re.split(r",\s*(?=[^,=]+=[^,=]+$)|,\s*(?=-?\d*[a-zA-Z])", tail)
    eqs: list[tuple[str, str]] = []
    for part in parts:
        part = part.strip().strip(",").strip()
        if not part or "=" not in part:
            continue
        lhs, rhs = part.split("=", 1)
        lhs, rhs = lhs.strip(), rhs.strip()
        if lhs and rhs:
            eqs.append((lhs, rhs))
    return eqs or None


def _to_sympy_expr(s: str):
    s = s.strip()
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    s = s.replace("·", "*").replace("×", "*")
    s = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", s)
    s = re.sub(r"\)\(", r")*(", s)
    x, y = symbols("x y")
    local = {"x": x, "y": y}
    return eval(s, {"__builtins__": {}}, local)  # noqa: S307 — controlled school math


def solve_coordinate(question: str) -> str | None:
    eqs = _extract_system(question)
    if not eqs:
        return None
    x, y = symbols("x y")
    try:
        system = [Eq(_to_sympy_expr(lhs), _to_sympy_expr(rhs)) for lhs, rhs in eqs]
        sol = solve(system, [x, y], dict=True)
    except Exception:
        return None
    if not sol:
        return "нет решений"
    if len(sol) > 1:
        return None
    s0 = sol[0]
    if x not in s0 or y not in s0:
        return "нет решений"
    xv, yv = s0[x], s0[y]

    def _fmt(v) -> str:
        if v.is_Rational and v.q != 1:
            return f"{v.p}/{v.q}"
        if v.is_integer:
            return str(int(v))
        return str(round(float(v), 4)).rstrip("0").rstrip(".")

    return f"({_fmt(xv)}; {_fmt(yv)})"


def main() -> int:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 7
                  AND tm.tags->>'smart_verify_status' = 'needs_human_review'
                  AND tm.answer_type = 'coordinate'
                ORDER BY tm.id
            """),
        ).all()
    for tid, q, ans in rows:
        solved = solve_coordinate(q or "")
        print(f"{tid}")
        print(f"  stored: {ans!r}")
        print(f"  solved: {solved!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
