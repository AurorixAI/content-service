#!/usr/bin/env python3
"""Fix 3 G8 accuracy-critical tasks from final audit."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import to_answer_latex
from src.pipeline.distractor_gate import validate_distractor_set

log = logging.getLogger("fix_g8_accuracy_step1")
logging.basicConfig(level=logging.INFO, format="%(message)s")

ERR_COMPARE = "Ошибка при сравнении корней: неверно вынесли множитель под корень"
ERR_EQ = "Ошибка при преобразовании уравнения к стандартному виду"

FIXES = {
    "G8_ALG_22_346.4": {
        "answer": "5x^2 + 1 = 0",
        "answer_type": "equation_solution",
        "distractors": [
            ("5x^2 - 15 = 0", ERR_EQ),
            ("5x^2 - 11 = 0", ERR_EQ),
            ("9x^2 - 15 = 0", ERR_EQ),
        ],
    },
    "G8_TB_18_408.2": {
        "answer": r"\sqrt{24} = \frac{1}{3}\sqrt{216}",
        "answer_type": "inequality",
        "input_mode": "mcq",
        "distractors": [
            (r"\sqrt{24} > \frac{1}{3}\sqrt{216}", ERR_COMPARE),
            (r"\sqrt{24} < \frac{1}{3}\sqrt{216}", ERR_COMPARE),
            ("Выражения невозможно сравнить, так как под корнями разные числа", ERR_COMPARE),
        ],
    },
    "G8_TB_18_408.3": {
        "answer": r"\frac{1}{3}\sqrt{54} = \frac{1}{5}\sqrt{150}",
        "answer_type": "inequality",
        "input_mode": "mcq",
        "distractors": [
            (r"\frac{1}{3}\sqrt{54} > \frac{1}{5}\sqrt{150}", ERR_COMPARE),
            (r"\frac{1}{3}\sqrt{54} < \frac{1}{5}\sqrt{150}", ERR_COMPARE),
            (r"\frac{1}{3}\sqrt{54} \neq \frac{1}{5}\sqrt{150}", ERR_COMPARE),
        ],
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    ok = fail = 0

    for tid, spec in FIXES.items():
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT question_text, tags FROM tasks_master WHERE id=:id"),
                {"id": tid},
            ).mappings().first()
        if not row:
            log.error("%s not found", tid)
            fail += 1
            continue

        ans = spec["answer"]
        atype = spec["answer_type"]
        manual = [
            {"value": v, "error_logic": el, "explanation": el}
            for v, el in spec["distractors"]
        ]
        acc, rej = validate_distractor_set(
            manual,
            question=row["question_text"] or "",
            correct_answer=ans,
            answer_type=atype,
            max_count=3,
            skip_l3=True,
        )
        log.info("%s A=%s dist=%s", tid, ans, [a["value"][:40] for a in acc])
        if rej:
            log.info("  rejected=%s", [(r["value"][:35], r.get("gate_reason")) for r in rej])
        if len(acc) < 2:
            fail += 1
            continue

        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        tags.pop("smart_verify_error", None)
        tags["smart_verify_status"] = "verified_corrected"
        tags["choices_complete"] = True
        tags["distractor_manual"] = "accuracy_step1"
        if spec.get("input_mode"):
            tags["input_mode"] = spec["input_mode"]

        latex = to_answer_latex(ans, atype) or ""
        if args.dry_run:
            ok += 1
            continue

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        correct_answer_latex = :latex,
                        answer_type = :atype,
                        distractor_meta = cast(:dmeta AS jsonb),
                        tags = cast(:tags AS jsonb),
                        verification_status = 'verified',
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": tid,
                    "ans": ans,
                    "latex": latex,
                    "atype": atype,
                    "dmeta": json.dumps(acc[:3], ensure_ascii=False),
                    "tags": json.dumps(tags, ensure_ascii=False),
                },
            )
        ok += 1

    log.info("Done: ok=%d fail=%d", ok, fail)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
