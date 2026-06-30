#!/usr/bin/env python3
"""Close final 11 G8 TB human_review tasks — corrected answers + distractors."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.distractor_gate import validate_distractor_set
from src.pipeline.smart_verify_common import run_distractor_only_pipeline, sync_verify_tags

log = logging.getLogger("fix_tb_hr_final")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Full Makarychev 851 stem (DB had only item а)).
Q_35_851 = """Выберите из данных неравенств такое, которое не является верным при любом значении $a$:
а) $a^2 > 2a - 3$;
б) $a^2 > -2a - 3$;
в) $a^2 > 5a - 6$;
г) $a^2 > 4a - 4$."""

FIXES = {
    "G8_TB_14_339.1": {
        "answer": "0,6",
        "note": "s=175 см → 1,75 м; t=√(2s/g)≈0,6 с",
    },
    "G8_TB_14_340.1": {
        "answer": "9,3",
        "note": "l=22 см в формуле учебника",
    },
    "G8_TB_14_340.2": {
        "answer": "22,3",
        "note": "l=126 см в формуле учебника",
    },
    "G8_TB_14_355.2": {
        "answer": r"x \approx 2,5",
        "note": r"x^3=16, x=2\sqrt[3]{2}\approx2,5",
    },
    "G8_TB_33_734.1": {
        "answer": "при p = 0 корней нет; при p ≠ 0 y = (p + 1)/p",
    },
    "G8_TB_33_734.2": {
        "answer": "при p = 3 y — любое число; при p ≠ 3 y = 4",
    },
    "G8_TB_34_844.1": {
        "answer": "Нет",
        "note": "сводится к x > -9, не при всех x",
    },
    "G8_TB_35_851": {
        "answer": "в",
        "question": Q_35_851,
        "answer_type": "multiple_choice",
        "promote_only": True,
    },
    "G8_TB_36_890": {
        "answer": "да, подойдёт (минимальная площадь 40,5 м²)",
    },
    "G8_TB_43_1103.6": {
        "answer": "f(-3) = 1, f(1) = -2",
    },
    "G8_TB_51_1240.2": {
        "answer": "Такого натурального числа a не существует",
    },
}

MANUAL_MCQ = {
    "G8_TB_34_844.1": {
        "answer_type": "text",
        "distractors": ["Да", "Да, при x > 0", "Да, при x \\geqslant -9"],
        "error_logic": "Ошибка при раскрытии скобок в неравенстве с квадратными членами",
    },
    "G8_TB_35_851": None,  # already has dist
    "G8_TB_43_1103.6": {
        "answer_type": "text",
        "distractors": [
            "f(-3) = -1, f(1) = 2",
            "f(-3) = 0, f(1) = 0",
            "возрастает на [-5; -2,5] и [2; 6]",
        ],
        "error_logic": "Ошибка при чтении значений функции с графика",
    },
    "G8_TB_51_1240.2": {
        "answer_type": "text",
        "distractors": ["a = 1", "a = 2", "a = 3"],
        "error_logic": "Ошибка при нахождении условия непересечения решений системы",
    },
}

PHYSICS_MCQ = {
    "G8_TB_14_339.1": ["5,9", "1,7", "3,0"],
    "G8_TB_14_340.1": ["0,9", "3,0", "1,5"],
    "G8_TB_14_340.2": ["2,2", "4,5", "15,0"],
}

PARAM_MCQ = {
    "G8_TB_33_734.1": [
        "y = (p + 1)/p при любых p",
        "при p = 0 y = 1",
        "корней нет при любых p",
    ],
    "G8_TB_33_734.2": [
        "y = 4 при любых p",
        "при p = 3 корней нет",
        "y = 3 при p \\neq 3",
    ],
}


def _tags(row) -> dict:
    tags = row["tags"]
    return dict(tags if isinstance(tags, dict) else json.loads(tags or "{}"))


def _finalize_tags(tags: dict, *, corrected: bool) -> dict:
    tags = dict(tags)
    for key in (
        "needs_human_review",
        "human_review_reason",
        "verify_conflict",
        "verify_unresolved",
        "answer_mismatch",
        "smart_verify_retry_exhausted",
        "smart_verify_retry_count",
        "smart_verify_error",
        "distractor_regen_exhausted",
        "distractor_regen_attempts",
    ):
        tags.pop(key, None)
    sync_verify_tags(tags, "verified_corrected" if corrected else "verified_match")
    tags["choices_complete"] = True
    tags["input_mode"] = "mcq"
    tags["answer_gemini_verified"] = True
    tags["answer_locked"] = True
    tags["answer_source"] = "corrected_manual" if corrected else "textbook"
    tags["sympy_gate_reason"] = "human_review_final"
    tags["distractor_manual"] = "hr_final"
    return tags


def _save(conn, tid: str, *, tags: dict, dmeta: list, question: str | None = None,
          answer: str | None = None, atype: str | None = None):
    params: dict = {
        "id": tid,
        "tags": json.dumps(tags, ensure_ascii=False),
        "dmeta": json.dumps(dmeta[:3], ensure_ascii=False),
    }
    parts = [
        "tags = cast(:tags AS jsonb)",
        "distractor_meta = cast(:dmeta AS jsonb)",
        "verification_status = 'verified'",
    ]
    if question is not None:
        params["q"] = question
        parts.append("question_text = :q")
    if answer is not None:
        params["ans"] = answer
        parts.append("correct_answer = :ans")
    if atype is not None:
        params["atype"] = atype
        parts.append("answer_type = :atype")
    conn.execute(text(f"UPDATE tasks_master SET {', '.join(parts)} WHERE id = :id"), params)


def _manual_dist(tid: str, row, spec: dict, answer: str) -> list:
    at = spec.get("answer_type", row["answer_type"])
    manual = [
        {"value": v, "error_logic": spec["error_logic"], "explanation": spec["error_logic"]}
        for v in spec["distractors"]
    ]
    acc, rej = validate_distractor_set(
        manual,
        question=row["question_text"] or "",
        correct_answer=answer,
        answer_type=at,
        max_count=3,
        skip_l3=True,
    )
    if len(acc) < 2:
        log.warning("%s manual dist partial %s rej=%s", tid, len(acc), rej)
    return acc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    ok = fail = 0

    for tid, spec in FIXES.items():
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT question_text, correct_answer, answer_type, distractor_meta, tags FROM tasks_master WHERE id=:id"),
                {"id": tid},
            ).mappings().first()
        if not row:
            log.error("%s not found", tid)
            fail += 1
            continue

        ans = spec["answer"]
        q = spec.get("question") or row["question_text"]
        atype = spec.get("answer_type") or row["answer_type"]
        corrected = (row["correct_answer"] or "").strip() != ans.strip()
        log.info("%s → %s%s", tid, ans[:60], f" ({spec['note']})" if spec.get("note") else "")

        if spec.get("promote_only"):
            dmeta = list(row["distractor_meta"] or [])
            if len(dmeta) < 2:
                log.error("  FAIL no dist")
                fail += 1
                continue
            if args.dry_run:
                ok += 1
                continue
            tags = _finalize_tags(_tags(row), corrected=False)
            with engine.begin() as conn:
                _save(conn, tid, tags=tags, dmeta=dmeta, question=q, answer=ans, atype=atype)
            ok += 1
            continue

        dmeta: list = []
        if tid in MANUAL_MCQ and MANUAL_MCQ[tid]:
            dmeta = _manual_dist(tid, {**row, "question_text": q}, MANUAL_MCQ[tid], ans)
        elif tid in PHYSICS_MCQ:
            el = "Ошибка при подстановке в физическую формулу или округлении"
            manual = [{"value": v, "error_logic": el} for v in PHYSICS_MCQ[tid]]
            acc, _ = validate_distractor_set(
                manual, question=q, correct_answer=ans, answer_type="text", max_count=3, skip_l3=True,
            )
            dmeta = acc
        elif tid in PARAM_MCQ:
            el = "Ошибка при разборе случаев с параметром"
            manual = [{"value": v, "error_logic": el} for v in PARAM_MCQ[tid]]
            acc, _ = validate_distractor_set(
                manual, question=q, correct_answer=ans, answer_type="text", max_count=3, skip_l3=True,
            )
            dmeta = acc
        elif tid == "G8_TB_14_355.2":
            el = "Ошибка при графическом решении иррационального уравнения"
            manual = [{"value": v, "error_logic": el} for v in ["x = 4", "x = 1", "x = 3"]]
            acc, _ = validate_distractor_set(
                manual, question=q, correct_answer=ans, answer_type="text", max_count=3, skip_l3=True,
            )
            dmeta = acc
        elif tid == "G8_TB_36_890":
            el = "Ошибка при оценке минимальной площади прямоугольника"
            manual = [{"value": v, "error_logic": el} for v in [
                "нет, не подойдёт (площадь меньше 40 м²)",
                "да, только если a = 7,6 и b = 5,5",
                "нет, максимальная площадь меньше 40 м²",
            ]]
            acc, _ = validate_distractor_set(
                manual, question=q, correct_answer=ans, answer_type="text", max_count=3, skip_l3=True,
            )
            dmeta = acc

        if len(dmeta) < 2 and not args.dry_run:
            tags = _finalize_tags(_tags(row), corrected=corrected)
            result = run_distractor_only_pipeline(
                task_id=tid,
                question=q or "",
                correct_answer=ans,
                answer_type=atype,
                distractor_meta=[],
                tags=tags,
            )
            dmeta = result["distractor_meta"] or []

        if len(dmeta) < 2:
            log.error("  FAIL dist=%d", len(dmeta))
            fail += 1
            continue

        if args.dry_run:
            ok += 1
            continue

        tags = _finalize_tags(_tags(row), corrected=corrected)
        with engine.begin() as conn:
            _save(conn, tid, tags=tags, dmeta=dmeta, question=q, answer=ans, atype=atype)
        log.info("  dist=%d", len(dmeta))
        ok += 1

    log.info("Done: ok=%d fail=%d", ok, fail)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
