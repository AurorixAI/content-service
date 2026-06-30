#!/usr/bin/env python3
"""Trim compound OCR tails from 5 G8 TB split children."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import to_answer_latex
from src.pipeline.compound_repair import trim_orphan_question_tail

log = logging.getLogger("fix_g8_compound_tails")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Manual overrides where auto-trim is insufficient.
MANUAL = {
    "G8_TB_43_1100.2": {
        "question": (
            "На рисунке 64 изображён график функции y = f(x), где -7 <= x <= 5. Укажите:\n"
            "в) промежутки, на которых функция возрастает, и промежутки, на которых она убывает;\n"
            "г) наибольшее и наименьшее значения функции."
        ),
    },
    "G8_TB_18_405.4.2": {
        "question": (
            "Представьте выражение в виде арифметического квадратного корня "
            "или выражения, ему противоположного:\n"
            r"$-\frac{1}{2}\sqrt{12x}$"
        ),
        "answer": r"-\sqrt{3x}",
        "answer_type": "expression",
    },
    "G8_TB_2_11.1": {
        "answer": "любое число",
    },
}

AUTO_TRIM = [
    "G8_TB_20_510.4",
    "G8_TB_43_1100.1",
    "G8_TB_2_11.1",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    ok = 0

    all_ids = list(dict.fromkeys(AUTO_TRIM + list(MANUAL.keys())))
    for tid in all_ids:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT question_text, correct_answer, answer_type, tags "
                    "FROM tasks_master WHERE id=:id"
                ),
                {"id": tid},
            ).mappings().first()
        if not row:
            log.error("%s not found", tid)
            continue

        spec = MANUAL.get(tid, {})
        q = spec.get("question")
        if not q and tid in AUTO_TRIM:
            q, changed = trim_orphan_question_tail(row["question_text"] or "")
            if not changed and tid not in MANUAL:
                log.info("%s no trim needed", tid)
                continue
        elif not q:
            q = row["question_text"]

        ans = spec.get("answer", row["correct_answer"])
        atype = spec.get("answer_type", row["answer_type"])
        latex = to_answer_latex(ans, atype) or ""

        log.info("%s\n  Q: %s\n  A: %s", tid, (q or "")[:80], ans)
        if args.dry_run:
            ok += 1
            continue

        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        tags["compound_tail_trimmed"] = True
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET question_text = :q,
                        correct_answer = :ans,
                        correct_answer_latex = :latex,
                        answer_type = :atype,
                        tags = cast(:tags AS jsonb),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": tid,
                    "q": q,
                    "ans": ans,
                    "latex": latex,
                    "atype": atype,
                    "tags": json.dumps(tags, ensure_ascii=False),
                },
            )
        ok += 1

    log.info("Done: ok=%d", ok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
