#!/usr/bin/env python3
"""Fix 4 G8 TB split siblings — same families as scratch step1."""
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

log = logging.getLogger("fix_tb_scratch_step2")
logging.basicConfig(level=logging.INFO, format="%(message)s")

ERR_COMPARE = "Ошибка при сравнении корней: неверно вынесли множитель под корень"
ERR_RATIONAL = "Ошибка при освобождении знаменателя от иррациональности"
ERR_EXPR = "Арифметическая ошибка при преобразовании выражения"

FIXES: dict[str, dict] = {
    "G8_TB_18_407.2.1": {
        "answer": r"5\sqrt{4} > 4\sqrt{5}",
        "answer_type": "inequality",
        "input_mode": "mcq",
        "keep_distractors": True,
    },
    "G8_TB_18_407.4.1": {
        "answer": r"2\sqrt{5} > 3\sqrt{2}",
        "answer_type": "inequality",
        "input_mode": "mcq",
        "distractors": [
            (r"2\sqrt{5} < 3\sqrt{2}", ERR_COMPARE),
            (r"2\sqrt{5} = 3\sqrt{2}", ERR_COMPARE),
            (
                r"2\sqrt{5} < 3\sqrt{2}, так как \sqrt{10} < \sqrt{12}",
                ERR_COMPARE,
            ),
        ],
    },
    "G8_TB_18_405.2.1": {
        "answer": r"-\sqrt{2}",
        "answer_type": "expression",
        "distractors": [
            (r"-\sqrt{0,2}", ERR_EXPR),
            (r"\sqrt{-2}", ERR_EXPR),
            (r"-\sqrt{20}", ERR_EXPR),
        ],
    },
    "G8_TB_18_424.4.1": {
        "answer": r"\frac{2\sqrt{y}}{7y}",
        "answer_type": "expression",
        "distractors": [
            (r"\frac{2\sqrt{y}}{49y}", ERR_RATIONAL),
            (r"\frac{14\sqrt{y}}{y}", ERR_RATIONAL),
            (r"\frac{2}{7y}", ERR_RATIONAL),
        ],
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
        q = row["question_text"] or ""

        if spec.get("keep_distractors"):
            dmeta = row["distractor_meta"] or []
            if isinstance(dmeta, str):
                dmeta = json.loads(dmeta)
            acc, rej = validate_distractor_set(
                dmeta,
                question=q,
                correct_answer=ans,
                answer_type=atype,
                max_count=3,
                skip_l3=True,
            )
            if rej:
                log.info("%s rejected=%s", tid, [(r["value"][:40], r.get("gate_reason")) for r in rej])
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

        log.info("%s A=%s type=%s dist=%s", tid, ans, atype, len(acc))
        if len(acc) < 2:
            log.error("  FAIL need >=2 distractors")
            fail += 1
            continue

        latex = to_answer_latex(ans, atype) or ""
        tags = _tags(row)
        _clear_retry_tags(tags)
        prev = tags.get("smart_verify_status", "")
        if prev in ("generated_from_scratch",) or prev.startswith("failed"):
            tags["smart_verify_status"] = "verified_corrected"
        elif prev == "verified_match":
            tags["smart_verify_status"] = "verified_corrected"
        tags["choices_complete"] = True
        tags["distractor_manual"] = "scratch_step2"
        if spec.get("input_mode"):
            tags["input_mode"] = spec["input_mode"]

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
