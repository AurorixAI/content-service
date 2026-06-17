#!/usr/bin/env python3
"""Quick spot-check: re-solve sample tasks with Gemini and compare to stored answers."""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, "/app")

from src.pipeline.enrichment import AIAnswerSolver
from src.pipeline.models import ExtractedTask

SAMPLES = [
    ("5", "120", "exact_number",
     "Зная, что a - 5/a = 2, найдите значение выражения a^2 + 25/a^2.",
     "14"),
    ("5", "110", "expression",
     "Выполните умножение:\nа) (5/(3a)) * (2b/3);\nб) (5a/(8y)) * (7/10);\nв) (b^2/10) * (4/b^2);\nг) (3/(2c)) * (c/2).",
     "а) 10b/(9a); б) 7a/(16y); в) b/2; г) 3/(4c)"),
    ("6", "131", "exact_number",
     "Упростите выражение (a^2 - 4ac - 3bc)/(a^2 - ab + bc - ac) + (a + 3b)/(b - a) + (a + 2c)/(a - c).",
     "1"),
    ("6", "133", "equation_solution",
     "Выразите x через a и b:\nа) 3x + b = a;\nб) b - 7x = a - b;\nв) x/a + 1 = b;\nг) b - x/10 = a.",
     "а) x = (a - b)/3; б) x = (2b - a)/7; в) x = a(b - 1); г) x = 10(b - a)"),
    ("7", "147", "exact_number",
     "От пристани против течения реки отправилась моторная лодка, собственная скорость 10 км/ч. "
     "Через 45 мин мотор испортился, течение за 3 ч принесло обратно. Какова скорость течения реки?",
     "2"),
    ("7", "153", "exact_number",
     "Выполните действия:\nа) (a^2-9)/(2a^2+1) * ((6a+1)/(a-3) + (6a-1)/(a+3));\n"
     "б) ((5x+y)/(x-5y) + (5x-y)/(x+5y)) : (x^2+y^2)/(x^2-25y^2).",
     "а) 6; б) 10"),
]


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", "", s)
    s = s.replace("−", "-").replace("–", "-")
    return s


def main() -> int:
    solver = AIAnswerSolver()
    results = []
    for para, ex, atype, q, stored in SAMPLES:
        task = ExtractedTask(
            temp_id=f"t_{para}_{ex}",
            question_text=q,
            answer_type=atype,
            answer_raw="",
        )
        solved = solver.solve(task)
        fresh = (solved.answer_raw or "").strip()
        sn, fn = _norm(stored), _norm(fresh)
        exact = bool(fresh) and sn == fn
        partial = bool(fresh) and (sn in fn or fn in sn or sn[:20] == fn[:20])
        results.append({
            "section": para,
            "exercise": ex,
            "type": atype,
            "stored": stored,
            "gemini_retest": fresh or "(empty)",
            "exact_match": exact,
            "partial_match": partial and not exact,
        })
    print(json.dumps(results, ensure_ascii=False, indent=2))
    ok = sum(1 for r in results if r["exact_match"])
    print(f"\n# exact: {ok}/{len(results)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
