#!/usr/bin/env python3
"""Fix G8 TB failed batch 1 — orphans, MCQ yes/no, integer-list MCQ, verify reset."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.compound_repair import trim_orphan_question_tail
from src.pipeline.distractor_gate import validate_distractor_set
from src.pipeline.smart_verify_common import run_distractor_only_pipeline

log = logging.getLogger("fix_tb_failed_step1")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Empty split children — recover answer + trim orphan question tail where needed.
ORPHAN_FIXES = {
    "G8_TB_2_27.3.2": {
        "answer": "-8b/(3c)",
        "trim": False,
    },
    "G8_TB_17_403.4.4": {
        "answer": r"\sqrt{a^2 x^2}",
        "trim": False,
    },
    "G8_TB_17_403.4.5": {
        "answer": r"\sqrt{m^7}",
        "trim": True,
    },
    "G8_TB_3_53.4.2": {
        "answer": "(x + 5)^2",
        "trim": True,
    },
    "G8_TB_2_25.1": {
        "answer": "x, 2/3",
        "trim_labeled": True,
        "labeled_cut": r";\s*б\)",
    },
}

MCQ_YESNO = {
    "G8_TB_31_696.1": {
        "answer": "да",
        "distractors": ["нет"],
        "error_logic": "Неверно проверил, подставив пару чисел в систему уравнений",
    },
    "G8_TB_31_696.2": {
        "answer": "нет",
        "distractors": ["да"],
        "error_logic": "Неверно проверил, подставив пару чисел в систему уравнений",
    },
}

# Verified answer OK but stuck in failed_at_sympy — keep existing distractors.
VERIFY_RESET = ["G8_TB_27_648"]

MANUAL_MCQ = {
    "G8_TB_40_986.2": {
        "answer_type": "inequality",
        "distractors": ["1, 2, 3, 4, 5", "3, 4, 5, 6, 7", "2, 3, 4, 5"],
        "error_logic": "Ошибка при решении системы неравенств и отборе целых решений",
    },
    "G8_TB_40_986.3": {
        "answer_type": "inequality",
        "distractors": ["-2, -1, 0, 1", "0, 1, 2, 3", "-1, 0, 1, 2"],
        "error_logic": "Ошибка при решении системы неравенств и отборе целых решений",
    },
    "G8_TB_41_1054.4.1": {
        "answer_type": "inequality",
        "distractors": ["1, 2, 3, 4", "3, 4, 5, 6", "2, 3, 4"],
        "error_logic": "Ошибка при решении системы неравенств с дробными коэффициентами",
    },
    "G8_TB_39_944.4.1": {
        "answer_type": "inequality",
        "distractors": [r"y \geqslant 2", r"y \geqslant 3", r"y > 2,6"],
        "error_logic": "Ошибка при раскрытии скобок и переносе слагаемых в линейном неравенстве",
    },
    "G8_TB_40_956.1": {
        "answer_type": "inequality",
        "distractors": ["x > -3", "x > -4", "x \\geqslant -3,1"],
        "error_logic": "Ошибка при раскрытии скобок и решении линейного неравенства",
    },
    "G8_TB_40_968": {
        "answer_type": "inequality",
        "distractors": ["не более 25 км", "не более 28 км", "не более 24 км"],
        "error_logic": "Ошибка при составлении неравенства для задачи на движение по реке",
    },
    "G8_TB_41_1044.1": {
        "answer_type": "inequality",
        "distractors": ["x > 5", "x < 0", "x \\geqslant 1"],
        "error_logic": "Ошибка при раскрытии скобок в линейном неравенстве",
    },
    "G8_TB_40_961.1": {
        "answer_type": "set",
        "distractors": ["n = 1, 2, 3", "n = 2, 3, 4, 5", "n = 1, 2"],
        "error_logic": "Ошибка при решении неравенства с натуральными значениями n",
    },
    "G8_TB_40_961.2": {
        "answer_type": "set",
        "distractors": ["n = 1", "n = 1, 2, 3", "n = 3, 4"],
        "error_logic": "Ошибка при решении неравенства с натуральными значениями n",
    },
    "G8_TB_4_71": {
        "answer_type": "set",
        "distractors": ["m = -10, -1, 1, 10", "m = -11, 0, 1, 11", "m = -1, 1"],
        "error_logic": "Ошибка при поиске целых m, при которых дробь принимает целые значения",
    },
    "G8_TB_9_204": {
        "answer_type": "set",
        "distractors": ["a = 0, 2", "a = 1, 2", "a = 2, 3"],
        "error_logic": "Ошибка при выделении целой части алгебраической дроби",
    },
    "G8_TB_9_206.2": {
        "answer_type": "set",
        "distractors": [
            "(2; 3), (0; -8), (4; 2)",
            "(1; 2), (3; 4), (5; 6)",
            "(2; 3), (-2; -3), (4; 2)",
        ],
        "error_logic": "Пропустил или неверно нашёл пары целых решений уравнения",
    },
    "G8_TB_9_207": {
        "answer_type": "set",
        "distractors": [
            "(1; 2), (2; 7), (4; -7)",
            "(0; 1), (2; 5), (3; -4)",
            "(1; 2), (3; 5), (5; -2)",
        ],
        "error_logic": "Пропустил точки графика с целочисленными координатами",
    },
    "G8_TB_48_1183.2": {
        "answer_type": "fraction",
        "distractors": ["9/4 и 4/9", "-1/9 и -9"],
        "error_logic": "Ошибка при вычислении степени с отрицательным показателем",
    },
}


def _load_row(conn, tid: str):
    return conn.execute(
        text("SELECT id, question_text, correct_answer, answer_type, distractor_meta, tags FROM tasks_master WHERE id=:id"),
        {"id": tid},
    ).mappings().first()


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
    ):
        tags.pop(key, None)
    tags.pop("smart_verify_error", None)


def _save_verified(
    conn,
    tid: str,
    *,
    tags: dict,
    dmeta: list,
    question: str | None = None,
    answer: str | None = None,
    atype: str | None = None,
    mcq_only: bool = False,
):
    tags = dict(tags)
    _clear_retry_tags(tags)
    tags["smart_verify_status"] = tags.get("smart_verify_status") or "verified_match"
    if tags["smart_verify_status"].startswith("failed"):
        tags["smart_verify_status"] = "verified_corrected"
    tags["choices_complete"] = True
    if mcq_only:
        tags["input_mode"] = "mcq"
        tags["distractor_manual"] = "failed_step1"

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


def fix_orphans(engine, dry_run: bool) -> tuple[int, int]:
    ok = fail = 0
    for tid, spec in ORPHAN_FIXES.items():
        with engine.connect() as conn:
            row = _load_row(conn, tid)
        if not row:
            log.error("%s not found", tid)
            fail += 1
            continue

        q = row["question_text"] or ""
        if spec.get("trim"):
            q, _ = trim_orphan_question_tail(q)
        elif spec.get("trim_labeled"):
            import re
            m = re.search(spec["labeled_cut"], q, re.I)
            if m:
                q = q[: m.start()].rstrip().rstrip(";,")

        ans = spec["answer"]
        log.info("%s orphan → A=%s", tid, ans)
        if dry_run:
            ok += 1
            continue

        tags = _tags(row)
        _clear_retry_tags(tags)
        result = run_distractor_only_pipeline(
            task_id=tid,
            question=q,
            correct_answer=ans,
            answer_type="expression",
            distractor_meta=[],
            tags=tags,
        )
        dmeta = result["distractor_meta"] or []
        if len(dmeta) < 2:
            log.error("  FAIL dist=%d", len(dmeta))
            fail += 1
            continue

        with engine.begin() as conn:
            _save_verified(
                conn,
                tid,
                tags=result["tags"],
                dmeta=dmeta,
                question=q,
                answer=ans,
                atype="expression",
            )
        log.info("  dist=%d", len(dmeta))
        ok += 1
    return ok, fail


def fix_mcq_yesno(engine, dry_run: bool) -> tuple[int, int]:
    ok = fail = 0
    for tid, spec in MCQ_YESNO.items():
        with engine.connect() as conn:
            row = _load_row(conn, tid)
        if not row:
            fail += 1
            continue

        manual = [
            {"value": v, "error_logic": spec["error_logic"], "explanation": spec["error_logic"]}
            for v in spec["distractors"]
        ]
        acc, rej = validate_distractor_set(
            manual,
            question=row["question_text"] or "",
            correct_answer=spec["answer"],
            answer_type="multiple_choice",
            max_count=3,
            skip_l3=True,
        )
        log.info("%s yes/no → A=%s dist=%s", tid, spec["answer"], [a["value"] for a in acc])
        if len(acc) < 1:
            log.error("  FAIL %s", rej)
            fail += 1
            continue
        if dry_run:
            ok += 1
            continue

        tags = _tags(row)
        with engine.begin() as conn:
            _save_verified(
                conn,
                tid,
                tags=tags,
                dmeta=acc,
                answer=spec["answer"],
                atype="multiple_choice",
                mcq_only=True,
            )
        ok += 1
    return ok, fail


def fix_verify_reset(engine, dry_run: bool) -> tuple[int, int]:
    ok = fail = 0
    for tid in VERIFY_RESET:
        with engine.connect() as conn:
            row = _load_row(conn, tid)
        if not row:
            fail += 1
            continue
        dmeta = row["distractor_meta"] or []
        if isinstance(dmeta, str):
            dmeta = json.loads(dmeta)
        log.info("%s verify reset dist=%d", tid, len(dmeta))
        if len(dmeta) < 2:
            fail += 1
            continue
        if dry_run:
            ok += 1
            continue
        tags = _tags(row)
        with engine.begin() as conn:
            _save_verified(conn, tid, tags=tags, dmeta=dmeta)
        ok += 1
    return ok, fail


def fix_manual_mcq(engine, dry_run: bool) -> tuple[int, int]:
    ok = fail = 0
    for tid, spec in MANUAL_MCQ.items():
        with engine.connect() as conn:
            row = _load_row(conn, tid)
        if not row:
            fail += 1
            continue

        ans = (row["correct_answer"] or "").strip()
        at = spec["answer_type"]
        manual = [
            {"value": v, "error_logic": spec["error_logic"], "explanation": spec["error_logic"]}
            for v in spec["distractors"]
        ]
        acc, rej = validate_distractor_set(
            manual,
            question=row["question_text"] or "",
            correct_answer=ans,
            answer_type=at,
            max_count=3,
            skip_l3=True,
        )
        log.info("%s manual MCQ A=%s dist=%s", tid, ans[:40], [a["value"] for a in acc])
        if rej:
            log.info("  rejected=%s", [(r["value"], r.get("gate_reason")) for r in rej])
        if len(acc) < 2:
            fail += 1
            continue
        if dry_run:
            ok += 1
            continue

        tags = _tags(row)
        with engine.begin() as conn:
            _save_verified(conn, tid, tags=tags, dmeta=acc, mcq_only=True)
        ok += 1
    return ok, fail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    totals = [0, 0]
    for fn in (fix_orphans, fix_mcq_yesno, fix_verify_reset, fix_manual_mcq):
        ok, fail = fn(engine, args.dry_run)
        totals[0] += ok
        totals[1] += fail

    log.info("Done: ok=%d fail=%d", totals[0], totals[1])
    return 0 if totals[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
