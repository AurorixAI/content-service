#!/usr/bin/env python3
"""Lock stable G7 proof distractors — no regen, no queue churn."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from scripts.fix_g7_dist_hard import MANUAL, STABLE_LOCK_IDS, _build_meta
from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import enrich_distractor_latex, to_answer_latex
from src.pipeline.distractor_gate import validate_distractor_set


def lock_one(engine, tid: str) -> bool:
    manual = MANUAL.get(tid)
    if not manual:
        print(f"SKIP {tid}: no manual distractors")
        return False
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT question_text, correct_answer, answer_type, tags "
                "FROM tasks_master WHERE id = :id"
            ),
            {"id": tid},
        ).fetchone()
    if not row:
        print(f"MISSING {tid}")
        return False
    question, answer, atype, tags_raw = row
    tags = dict(tags_raw or {})
    raw = [{"value": v, "error_logic": el} for v, el in manual]
    accepted, rejected = validate_distractor_set(
        raw,
        question=question or "",
        correct_answer=answer or "",
        answer_type=atype or "text",
        max_count=3,
        skip_l3=True,
    )
    if len(accepted) < 2:
        print(f"FAIL {tid}: gate {len(accepted)}")
        for r in rejected[:3]:
            print(f"  {r.get('gate_reason')}: {str(r.get('value', ''))[:50]}")
        return False
    dmeta = enrich_distractor_latex(_build_meta(accepted), atype or "text")
    cal = to_answer_latex(answer or "", atype or "text")
    tags["choices_complete"] = True
    tags["distractor_locked"] = True
    tags["answer_locked"] = True
    tags["dist_stable_lock"] = True
    tags["distractor_gate_passed"] = len(dmeta)
    for key in (
        "distractor_regen_pending",
        "distractor_regen_exhausted",
        "distractor_regen_attempts",
        "distractor_gate_rejected",
    ):
        tags.pop(key, None)
    with engine.begin() as conn:
        rc = conn.execute(
            text("""
                UPDATE tasks_master
                SET distractor_meta = cast(:dmeta AS jsonb),
                    correct_answer_latex = :cal,
                    tags = cast(:tags AS jsonb),
                    updated_at = NOW()
                WHERE id = :id
            """),
            {
                "id": tid,
                "dmeta": json.dumps(dmeta, ensure_ascii=False),
                "cal": cal,
                "tags": json.dumps(tags, ensure_ascii=False),
            },
        )
    print(f"LOCK {tid} dist={len(dmeta)} cal_len={len(cal)} rows={rc.rowcount}")
    return rc.rowcount == 1


def main() -> int:
    engine = create_engine(get_settings().database_url)
    ok = sum(lock_one(engine, tid) for tid in sorted(STABLE_LOCK_IDS))
    print(f"Done: {ok}/{len(STABLE_LOCK_IDS)}")
    return 0 if ok == len(STABLE_LOCK_IDS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
