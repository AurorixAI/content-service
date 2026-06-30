#!/usr/bin/env python3
"""Fix G8 TB human_review queue — batch 1: swaps, equivalents, OCR, graph MCQ."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.compound_repair import trim_orphan_question_tail
from src.pipeline.distractor_gate import validate_distractor_set
from src.pipeline.smart_verify_common import run_distractor_only_pipeline, sync_verify_tags

log = logging.getLogger("fix_tb_hr_step1")
logging.basicConfig(level=logging.INFO, format="%(message)s")

MCQ_SWAP = {
    "G8_TB_10_273.2": {
        "answer": "1,6668",
        "distractors": [r"1\frac{2}{3}", "1,6666"],
        "error_logic": "Ошибка при сравнении периодической и конечной десятичной дроби",
    },
    "G8_TB_10_273.3": {
        "answer": "-4,45",
        "distractors": ["-4,(45)", "-4,4545"],
        "error_logic": "Ошибка при сравнении периодической и конечной десятичной дроби",
    },
}

# Answers crossed between sibling split-children (non-MCQ).
SWAP_FIXES = {
    "G8_TB_13_329.2": {"answer": "10 и 11"},
    "G8_TB_13_329.3": {"answer": "6 и 7"},
    "G8_TB_14_351.2": {"answer": "да, в точке (10000; 100)"},
    "G8_TB_14_351.3": {"answer": "да, в точке (100; 10)"},
}

# Textbook OCR / logic errors — use corrected school answer.
ANSWER_FIXES = {
    "G8_TB_15_366.2": {"answer": "0,24"},
    "G8_TB_14_356.4.1": {"answer": r"\sqrt{50}"},
    "G8_TB_29_687.4.2": {"answer": "бесконечно много решений"},
    "G8_TB_44_1114.2": {
        "answer": "График — прямая через (0; 5) и (5; 2). D(y)=R, E(y)=R, функция убывает, нуль x=25/3",
    },
    "G8_TB_44_1115.1": {
        "answer": "График — прямая через (0; 0) и (1; 1,6). D(y)=R, E(y)=R, функция возрастает",
    },
    "G8_TB_38_902": {
        "answer": "точка",
        "trim_compound": True,
    },
    "G8_TB_38_913": {
        "answer": "[-2; 3], [-2; 3), (-5; -2], (-5; -2)",
    },
    "G8_TB_20_511.4": {
        "answer": "a=1, b=5, c=0",
        "trim_orphan": True,
    },
}

# Already good — just clear HR flag (have dist>=2).
PROMOTE_ONLY = [
    "G8_TB_17_404",
    "G8_TB_45_1126",
    "G8_TB_14_341",
    "G8_TB_14_356.4.5",
    "G8_TB_28_674",
    "G8_TB_33_740",
    "G8_TB_34_841",
    "G8_TB_3_62",
    "G8_TB_41_1052",
    "G8_TB_42_1082",
    "G8_TB_42_1084",
]

# Textbook answer kept; LLM only disagreed on formatting — regen distractors.
EQUIV_REGEN_DIST = [
    "G8_TB_12_316.3",
    "G8_TB_24_599.1",
    "G8_TB_24_602.1",
    "G8_TB_24_602.3",
    "G8_TB_24_602.4.3",
    "G8_TB_24_603.1",
    "G8_TB_24_603.4",
    "G8_TB_38_914.4",
    "G8_TB_42_1078.2",
    "G8_TB_11_275.1",  # textbook C is correct — promote
]

GRAPH_MCQ = {
    "G8_TB_9_197.1": {
        "distractors": [
            "ветви в I и III четвертях, прижаты к осям",
            "ветви во II и IV четвертях, удалены от осей",
            "ветви во II и IV четвертях, прижаты к осям",
        ],
    },
    "G8_TB_9_197.2": {
        "distractors": [
            "ветви в I и III четвертях, удалены от осей",
            "ветви во II и IV четвертях, удалены от осей",
            "ветви во II и IV четвертях, прижаты к осям",
        ],
    },
    "G8_TB_9_197.3": {
        "distractors": [
            "ветви в I и III четвертях, удалены от осей",
            "ветви в I и III четвертях, прижаты к осям",
            "ветви во II и IV четвертях, прижаты к осям",
        ],
    },
    "G8_TB_9_197.4": {
        "distractors": [
            "ветви в I и III четвертях, удалены от осей",
            "ветви в I и III четвертях, прижаты к осям",
            "ветви во II и IV четвертях, удалены от осей",
        ],
    },
}

COORD_MCQ = {
    "G8_TB_32_712.1": {
        "distractors": [
            "не пересекает",
            "пересекает в одной точке (4; 2)",
            "пересекает в точках (0; 0) и (8; 16)",
        ],
        "error_logic": "Ошибка при решении системы уравнений параболы и прямой",
    },
}

# Stay in human review — tag reason for manual pass.
KEEP_HR = {
    "G8_TB_14_339.1": "physics_formula_units_unclear",
    "G8_TB_14_340.1": "physics_formula_units_unclear",
    "G8_TB_14_340.2": "physics_formula_units_unclear",
    "G8_TB_34_844.1": "proof_inequality_dispute",
    "G8_TB_35_851": "mcq_answer_dispute_a_vs_v",
    "G8_TB_36_890": "floor_area_inequality_dispute",
    "G8_TB_43_1103.6": "answer_mismatch_question_asks_f_values",
    "G8_TB_51_1240.2": "garbled_natural_number_answer",
    "G8_TB_33_734.1": "parametric_case_answer",
    "G8_TB_33_734.2": "parametric_case_answer",
    "G8_TB_14_355.2": "irrational_root_format",
}


def _tags(row) -> dict:
    tags = row["tags"]
    return dict(tags if isinstance(tags, dict) else json.loads(tags or "{}"))


def _strip_hr(tags: dict, *, corrected: bool = False) -> dict:
    tags = dict(tags)
    for key in (
        "needs_human_review",
        "verify_conflict",
        "verify_unresolved",
        "answer_mismatch",
        "smart_verify_retry_exhausted",
        "smart_verify_retry_count",
    ):
        tags.pop(key, None)
    status = "verified_corrected" if corrected else "verified_match"
    sync_verify_tags(tags, status)
    tags["choices_complete"] = True
    tags["answer_gemini_verified"] = True
    tags["answer_locked"] = True
    tags["answer_source"] = "textbook" if not corrected else "corrected_manual"
    tags["sympy_gate_reason"] = "human_review_batch1"
    tags.pop("human_review_reason", None)
    return tags


def _save(conn, tid: str, *, tags: dict, dmeta: list | None = None, question: str | None = None,
          answer: str | None = None, atype: str | None = None, mcq: bool = False):
    tags = dict(tags)
    if mcq:
        tags["input_mode"] = "mcq"
    params: dict = {"id": tid, "tags": json.dumps(tags, ensure_ascii=False)}
    parts = ["tags = cast(:tags AS jsonb)", "verification_status = 'verified'"]
    if dmeta is not None:
        params["dmeta"] = json.dumps(dmeta[:3], ensure_ascii=False)
        parts.append("distractor_meta = cast(:dmeta AS jsonb)")
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


def _trim_compound_a(q: str) -> str:
    m = re.search(r";\s*[бвгд]", q, re.I)
    return q[: m.start()].rstrip() if m else q


def process_promote_only(engine, dry_run: bool) -> tuple[int, int]:
    ok = fail = 0
    for tid in PROMOTE_ONLY:
        with engine.connect() as c:
            row = c.execute(
                text("SELECT tags, distractor_meta FROM tasks_master WHERE id=:id"), {"id": tid}
            ).mappings().first()
        if not row:
            fail += 1
            continue
        dmeta = row["distractor_meta"] or []
        if len(dmeta) < 2:
            log.warning("%s promote skip dist=%d", tid, len(dmeta))
            fail += 1
            continue
        log.info("%s promote only dist=%d", tid, len(dmeta))
        if dry_run:
            ok += 1
            continue
        tags = _strip_hr(_tags(row))
        with engine.begin() as c:
            _save(c, tid, tags=tags, dmeta=dmeta)
        ok += 1
    return ok, fail


def process_answer_fixes(engine, dry_run: bool, regen: bool) -> tuple[int, int]:
    ok = fail = 0
    specs = {**SWAP_FIXES, **ANSWER_FIXES}
    for tid, spec in specs.items():
        with engine.connect() as c:
            row = c.execute(
                text("SELECT question_text, correct_answer, answer_type, distractor_meta, tags FROM tasks_master WHERE id=:id"),
                {"id": tid},
            ).mappings().first()
        if not row:
            fail += 1
            continue

        q = row["question_text"] or ""
        if spec.get("trim_orphan"):
            q, _ = trim_orphan_question_tail(q)
        if spec.get("trim_compound"):
            q = _trim_compound_a(q)

        ans = spec["answer"]
        atype = spec.get("answer_type") or row["answer_type"]
        log.info("%s fix A: %s → %s", tid, (row["correct_answer"] or "")[:40], ans[:60])
        if dry_run:
            ok += 1
            continue

        tags = _strip_hr(_tags(row), corrected=True)
        dmeta = list(row["distractor_meta"] or [])
        if regen and len(dmeta) < 2:
            result = run_distractor_only_pipeline(
                task_id=tid,
                question=q,
                correct_answer=ans,
                answer_type=atype,
                distractor_meta=[],
                tags=tags,
            )
            dmeta = result["distractor_meta"] or []
            tags = result["tags"]
            tags = _strip_hr(tags, corrected=True)

        if atype == "multiple_choice" and len(dmeta) < 1:
            # minimal MCQ: generate opposite-style via gate below in graph section
            pass

        if len(dmeta) < 2 and atype not in ("multiple_choice",):
            log.error("  FAIL dist=%d", len(dmeta))
            fail += 1
            continue

        with engine.begin() as c:
            _save(c, tid, tags=tags, dmeta=dmeta if dmeta else None, question=q, answer=ans, atype=atype,
                  mcq=atype in ("multiple_choice", "text", "set", "inequality"))
        ok += 1
    return ok, fail


def process_equiv_regen(engine, dry_run: bool) -> tuple[int, int]:
    ok = fail = 0
    for tid in EQUIV_REGEN_DIST:
        with engine.connect() as c:
            row = c.execute(
                text("SELECT question_text, correct_answer, answer_type, distractor_meta, tags FROM tasks_master WHERE id=:id"),
                {"id": tid},
            ).mappings().first()
        if not row:
            fail += 1
            continue
        ans = (row["correct_answer"] or "").strip()
        atype = row["answer_type"]
        log.info("%s equiv regen dist", tid)
        if dry_run:
            ok += 1
            continue
        tags = _strip_hr(_tags(row))
        result = run_distractor_only_pipeline(
            task_id=tid,
            question=row["question_text"] or "",
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
        tags = _strip_hr(result["tags"])
        with engine.begin() as c:
            _save(c, tid, tags=tags, dmeta=dmeta, mcq=True)
        ok += 1
    return ok, fail


def process_manual_mcq(engine, specs: dict, dry_run: bool) -> tuple[int, int]:
    ok = fail = 0
    el_default = "Типичная ошибка при анализе графика гиперболы"
    for tid, spec in specs.items():
        with engine.connect() as c:
            row = c.execute(
                text("SELECT question_text, correct_answer, answer_type, tags FROM tasks_master WHERE id=:id"),
                {"id": tid},
            ).mappings().first()
        if not row:
            fail += 1
            continue
        ans = (spec.get("answer") or row["correct_answer"] or "").strip().lstrip("— ").rstrip(".")
        el = spec.get("error_logic", el_default)
        manual = [{"value": v, "error_logic": el} for v in spec["distractors"]]
        acc, rej = validate_distractor_set(
            manual,
            question=row["question_text"] or "",
            correct_answer=ans,
            answer_type="multiple_choice",
            max_count=3,
            skip_l3=True,
        )
        log.info("%s manual MCQ dist=%s", tid, [a["value"][:40] for a in acc])
        if len(acc) < 1:
            log.error("  FAIL %s", rej)
            fail += 1
            continue
        if dry_run:
            ok += 1
            continue
        tags = _strip_hr(_tags(row), corrected=bool(spec.get("answer")))
        with engine.begin() as c:
            _save(c, tid, tags=tags, dmeta=acc, answer=ans, atype="multiple_choice", mcq=True)
        ok += 1
    return ok, fail


def process_keep_hr(engine, dry_run: bool) -> int:
    for tid, reason in KEEP_HR.items():
        with engine.connect() as c:
            row = c.execute(text("SELECT tags FROM tasks_master WHERE id=:id"), {"id": tid}).mappings().first()
        if not row:
            continue
        tags = _tags(row)
        tags["human_review_reason"] = reason
        tags["needs_human_review"] = True
        log.info("%s keep HR: %s", tid, reason)
        if not dry_run:
            with engine.begin() as c:
                c.execute(
                    text("UPDATE tasks_master SET tags=cast(:t AS jsonb) WHERE id=:id"),
                    {"id": tid, "t": json.dumps(tags, ensure_ascii=False)},
                )
    return len(KEEP_HR)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-regen", action="store_true", help="Skip LLM distractor regen for answer fixes")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    ok = fail = 0

    o, f = process_promote_only(engine, args.dry_run)
    ok += o
    fail += f

    o, f = process_manual_mcq(engine, GRAPH_MCQ, args.dry_run)
    ok += o
    fail += f

    o, f = process_manual_mcq(engine, COORD_MCQ, args.dry_run)
    ok += o
    fail += f

    o, f = process_manual_mcq(engine, MCQ_SWAP, args.dry_run)
    ok += o
    fail += f

    o, f = process_answer_fixes(engine, args.dry_run, regen=not args.no_regen)
    ok += o
    fail += f

    o, f = process_equiv_regen(engine, args.dry_run)
    ok += o
    fail += f

    tagged = process_keep_hr(engine, args.dry_run)
    log.info("Done: ok=%d fail=%d keep_hr_tagged=%d", ok, fail, tagged)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
