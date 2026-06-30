#!/usr/bin/env python3
"""Fix 11 G8 TB generated_from_scratch split children — answers, types, MCQ."""
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

log = logging.getLogger("fix_tb_scratch_step1")
logging.basicConfig(level=logging.INFO, format="%(message)s")

ERR_COMPARE = "Ошибка при сравнении корней: неверно вынесли множитель под корень"
ERR_RATIONAL = "Ошибка при освобождении знаменателя от иррациональности"
ERR_EXPR = "Арифметическая ошибка при преобразовании выражения"
ERR_EQ = "Ошибка при решении линейного уравнения"
ERR_NUM = "Арифметическая ошибка при вычислении"
ERR_TEXT = "Ошибка при анализе графика или свойств функции"

FIXES: dict[str, dict] = {
    "G8_TB_18_405.2.2": {
        "answer": r"-\sqrt{0,012a}",
        "answer_type": "expression",
        "distractors": [
            (r"-\sqrt{0,12a}", ERR_EXPR),
            (r"\sqrt{0,012a}", ERR_EXPR),
            (r"-\sqrt{0,0012a}", ERR_EXPR),
        ],
    },
    "G8_TB_18_407.2.2": {
        "answer": r"-\sqrt{14} > -3\sqrt{2}",
        "answer_type": "inequality",
        "distractors": [
            (r"-\sqrt{14} < -3\sqrt{2}", ERR_COMPARE),
            (r"-\sqrt{14} < -\sqrt{6}", ERR_COMPARE),
            (r"-\sqrt{14} = -3\sqrt{2}", ERR_COMPARE),
        ],
        "input_mode": "mcq",
    },
    "G8_TB_18_407.4.2": {
        "answer": r"-7\sqrt{0,17} < -11\sqrt{0,05}",
        "answer_type": "inequality",
        "distractors": [
            (r"-7\sqrt{0,17} > -11\sqrt{0,05}", ERR_COMPARE),
            (r"-7\sqrt{0,17} = -11\sqrt{0,05}", ERR_COMPARE),
            (r"-7\sqrt{0,17} > -11\sqrt{0,05}, так как 0,17 > 0,05", ERR_COMPARE),
        ],
        "input_mode": "mcq",
    },
    "G8_TB_18_419.4.2": {
        "answer": "2",
        "answer_type": "exact_number",
        "distractors": [
            ("-10", ERR_NUM),
            ("-14", ERR_NUM),
            ("22", ERR_NUM),
        ],
    },
    "G8_TB_18_424.4.2": {
        "answer": r"\frac{\sqrt{a-b}}{a-b}",
        "answer_type": "expression",
        "question": (
            "Освободитесь от иррациональности в знаменателе дроби:\n"
            r"$\frac{1}{\sqrt{a-b}}$"
        ),
        "distractors": [
            (r"\frac{\sqrt{a-b}}{a^2-b^2}", ERR_RATIONAL),
            (r"\frac{\sqrt{a+b}}{a-b}", ERR_RATIONAL),
            (r"\frac{1}{a-b}", ERR_RATIONAL),
        ],
    },
    "G8_TB_3_52.4.2": {
        "answer": r"x = -\frac{50}{7}",
        "answer_type": "equation_solution",
        "distractors": [
            ("-3.5", ERR_EQ),
            ("7.1428571429", ERR_EQ),
            ("-0.14", ERR_EQ),
        ],
    },
    "G8_TB_48_1185.3.2": {
        "answer": "6",
        "answer_type": "exact_number",
        "distractors": [
            ("11.83", ERR_NUM),
            ("18", ERR_NUM),
            ("11.5", ERR_NUM),
        ],
    },
    "G8_TB_48_1185.4.2": {
        "answer": "125",
        "answer_type": "exact_number",
        "distractors": [
            ("25.01", ERR_NUM),
            ("26", ERR_NUM),
            ("23", ERR_NUM),
        ],
    },
    "G8_TB_6_132.2": {
        "answer": r"\frac{151}{60}",
        "answer_type": "exact_number",
        "distractors": [
            ("2.616667", ERR_NUM),
            ("2.31", ERR_NUM),
            ("2.45", ERR_NUM),
        ],
    },
    "G8_TB_43_1100.2": {
        "answer": (
            "в) возрастает на [-7; -3] и [1; 5], убывает на [-3; 1]; "
            "г) наибольшее значение равно 5, наименьшее значение равно -2"
        ),
        "answer_type": "text",
        "keep_distractors": True,
        "input_mode": "mcq",
    },
    "G8_TB_44_1115.2": {
        "answer": (
            "График функции y = -0,4x — прямая, проходящая через начало координат (0; 0) "
            "и точку (5; -2). Свойства функции y = kx: при k > 0 функция возрастает, "
            "график расположен в I и III координатных четвертях; при k < 0 функция убывает, "
            "график расположен во II и IV координатных четвертях."
        ),
        "answer_type": "text",
        "keep_distractors": True,
        "input_mode": "mcq",
    },
}


def _tags(row) -> dict:
    tags = row["tags"]
    return tags if isinstance(tags, dict) else json.loads(tags or "{}")


def _clear_retry_tags(tags: dict) -> None:
    for key in (
        "distractor_regen_exhausted",
        "distractor_regen_attempts",
        "distractor_regen_pending",
        "smart_verify_retry_exhausted",
        "smart_verify_retry_count",
        "choices_complete",
        "smart_verify_error",
    ):
        tags.pop(key, None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    ok = fail = 0

    for tid, spec in FIXES.items():
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT question_text, correct_answer, answer_type, "
                    "distractor_meta, tags FROM tasks_master WHERE id=:id"
                ),
                {"id": tid},
            ).mappings().first()
        if not row:
            log.error("%s not found", tid)
            fail += 1
            continue

        ans = spec["answer"]
        atype = spec["answer_type"]
        q = spec.get("question") or (row["question_text"] or "")

        if spec.get("keep_distractors"):
            dmeta = row["distractor_meta"] or []
            if isinstance(dmeta, str):
                dmeta = json.loads(dmeta)
            acc = list(dmeta)
        else:
            manual = [
                {"value": v, "error_logic": el, "explanation": el}
                for v, el in spec["distractors"]
            ]
            acc, rej = validate_distractor_set(
                manual,
                question=q,
                correct_answer=ans,
                answer_type=atype,
                max_count=3,
                skip_l3=True,
            )
            if rej:
                log.info("%s rejected=%s", tid, [(r["value"][:40], r.get("gate_reason")) for r in rej])

        log.info("%s A=%s type=%s dist=%s", tid, ans[:60], atype, len(acc))
        if len(acc) < 2:
            log.error("  FAIL need >=2 distractors")
            fail += 1
            continue

        latex = to_answer_latex(ans, atype) or ""
        tags = _tags(row)
        _clear_retry_tags(tags)
        tags["smart_verify_status"] = "verified_corrected"
        tags["choices_complete"] = True
        tags["distractor_manual"] = "scratch_step1"
        if spec.get("input_mode"):
            tags["input_mode"] = spec["input_mode"]

        if args.dry_run:
            ok += 1
            continue

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET question_text = :q,
                        correct_answer = :ans,
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
                    "q": q,
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
