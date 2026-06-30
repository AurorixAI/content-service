#!/usr/bin/env python3
"""G8 ALG step 1 — close failed, HR, orphan compound tails."""
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
from src.pipeline.smart_verify_common import sync_verify_tags

log = logging.getLogger("fix_alg_step1")
logging.basicConfig(level=logging.INFO, format="%(message)s")

FAILED_MCQ = {
    "G8_ALG_16_241.3": {
        "answer": "5",
        "distractors": ["-3; 0", "нет таких чисел"],
        "error_logic": "Ошибка при решении системы неравенств и проверке чисел из списка",
    },
    "G8_ALG_16_242.1": {
        "answer": "-2; 0",
        "distractors": ["-2; 0; 1", "0; 1"],
        "error_logic": "Ошибка при решении системы неравенств и отборе решений из списка",
    },
}

HR_FIXES = {
    "G8_ALG_16_244.5": {"answer": "[-3; 1)"},
    "G8_ALG_19_292.5": {"answer": "нет"},
    "G8_ALG_22_347.6": {"answer": "из списка нет", "answer_type": "multiple_choice"},
    "G8_ALG_8_111.6": {"answer": "1/30"},
}

HR_PROMOTE = [
    "G8_ALG_32_546",
    "G8_ALG_32_547",
    "G8_ALG_32_550.4",
    "G8_ALG_32_563.2",
    "G8_ALG_32_565.1",
]

# Orphan OCR tail «; д)…» — trim question, keep atomic answer.
ORPHAN_TRIM = [
    "G8_ALG_8_106.1",
    "G8_ALG_8_106.2",
    "G8_ALG_8_106.5",
    "G8_ALG_8_107.5",
    "G8_ALG_8_108.5",
]


def _tags(row) -> dict:
    t = row["tags"]
    return dict(t if isinstance(t, dict) else json.loads(t or "{}"))


def _finalize(tags: dict, *, corrected: bool = False) -> dict:
    tags = dict(tags)
    for k in ("needs_human_review", "human_review_reason", "smart_verify_error",
              "smart_verify_retry_exhausted", "distractor_regen_exhausted"):
        tags.pop(k, None)
    sync_verify_tags(tags, "verified_corrected" if corrected else "verified_match")
    tags["choices_complete"] = True
    tags.pop("needs_compound_split", None)
    tags["sympy_gate_reason"] = "alg_step1"
    return tags


def _save(conn, tid, *, tags, dmeta=None, q=None, ans=None, atype=None, mcq=False):
    tags = dict(tags)
    if mcq:
        tags["input_mode"] = "mcq"
    p = {"id": tid, "tags": json.dumps(tags, ensure_ascii=False)}
    parts = ["tags = cast(:tags AS jsonb)", "verification_status = 'verified'"]
    if dmeta is not None:
        p["dmeta"] = json.dumps(dmeta[:3], ensure_ascii=False)
        parts.append("distractor_meta = cast(:dmeta AS jsonb)")
    if q is not None:
        p["q"] = q
        parts.append("question_text = :q")
    if ans is not None:
        p["ans"] = ans
        parts.append("correct_answer = :ans")
    if atype is not None:
        p["atype"] = atype
        parts.append("answer_type = :atype")
    conn.execute(text(f"UPDATE tasks_master SET {', '.join(parts)} WHERE id = :id"), p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    engine = create_engine(get_settings().database_url)
    ok = fail = 0

    for tid, spec in FAILED_MCQ.items():
        with engine.connect() as c:
            row = c.execute(
                text("SELECT question_text, correct_answer, answer_type, tags FROM tasks_master WHERE id=:id"),
                {"id": tid},
            ).mappings().first()
        ans = spec["answer"]
        manual = [{"value": v, "error_logic": spec["error_logic"]} for v in spec["distractors"]]
        acc, rej = validate_distractor_set(
            manual, question=row["question_text"], correct_answer=ans,
            answer_type="inequality", max_count=3, skip_l3=True,
        )
        log.info("%s failed→ A=%s dist=%s", tid, ans, [a["value"] for a in acc])
        if len(acc) < 2:
            log.error("  FAIL %s", rej)
            fail += 1
            continue
        if not args.dry_run:
            tags = _finalize(_tags(row), corrected=True)
            tags["input_mode"] = "mcq"
            with engine.begin() as c:
                _save(c, tid, tags=tags, dmeta=acc, ans=ans, atype="inequality", mcq=True)
        ok += 1

    for tid, spec in HR_FIXES.items():
        with engine.connect() as c:
            row = c.execute(
                text("SELECT question_text, correct_answer, answer_type, distractor_meta, tags FROM tasks_master WHERE id=:id"),
                {"id": tid},
            ).mappings().first()
        ans = spec["answer"]
        atype = spec.get("answer_type") or row["answer_type"]
        log.info("%s HR fix A=%s", tid, ans)
        if not args.dry_run:
            tags = _finalize(_tags(row), corrected=True)
            with engine.begin() as c:
                _save(c, tid, tags=tags, dmeta=row["distractor_meta"] or [], ans=ans, atype=atype,
                      mcq=atype in ("multiple_choice", "inequality"))
        ok += 1

    for tid in HR_PROMOTE:
        with engine.connect() as c:
            row = c.execute(
                text("SELECT distractor_meta, tags FROM tasks_master WHERE id=:id"),
                {"id": tid},
            ).mappings().first()
        dmeta = row["distractor_meta"] or []
        if len(dmeta) < 2:
            fail += 1
            continue
        log.info("%s HR promote dist=%d", tid, len(dmeta))
        if not args.dry_run:
            with engine.begin() as c:
                _save(c, tid, tags=_finalize(_tags(row)), dmeta=dmeta)
        ok += 1

    for tid in ORPHAN_TRIM:
        with engine.connect() as c:
            row = c.execute(
                text("SELECT question_text, correct_answer, answer_type, distractor_meta, tags FROM tasks_master WHERE id=:id"),
                {"id": tid},
            ).mappings().first()
        q, trimmed = trim_orphan_question_tail(row["question_text"] or "")
        if not trimmed:
            log.info("%s orphan skip (no tail)", tid)
            continue
        log.info("%s orphan trim", tid)
        if not args.dry_run:
            tags = _finalize(_tags(row))
            with engine.begin() as c:
                _save(c, tid, tags=tags, dmeta=row["distractor_meta"] or [], q=q)
        ok += 1

    log.info("Done ok=%d fail=%d", ok, fail)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
