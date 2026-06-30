#!/usr/bin/env python3
"""Fix G8 TB group B: inequality MCQ distractors (manual + gate-safe)."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.distractor_gate import validate_distractor_set

log = logging.getLogger("fix_tb_group_b")
logging.basicConfig(level=logging.INFO, format="%(message)s")

GROUP_B = {
    "G8_TB_36_881.1": {
        "distractors": ["3 > 16", "21 < 3", "20 < 2"],
    },
    "G8_TB_36_881.2": {
        "distractors": ["9 < 2", "-9 > -3", "4 < -2"],
    },
    "G8_TB_36_882.1": {
        "distractors": ["20 < 7", "18 < 6", "9 > 12"],
    },
    "G8_TB_36_882.2": {
        "distractors": ["8 < 5", "10 < 5", "4 < 2"],
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    ok = fail = 0

    for tid, spec in GROUP_B.items():
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT question_text, correct_answer, tags FROM tasks_master WHERE id=:id"),
                {"id": tid},
            ).mappings().first()
        if not row:
            log.error("%s not found", tid)
            fail += 1
            continue

        ans = row["correct_answer"] or ""
        q = row["question_text"] or ""
        manual = [
            {
                "value": v,
                "error_logic": "Ошибка при почленном сложении или умножении неравенств",
                "explanation": "Типичная ошибка с левыми/правыми частями или знаком",
            }
            for v in spec["distractors"]
        ]
        acc, rej = validate_distractor_set(
            manual,
            question=q,
            correct_answer=ans,
            answer_type="inequality",
            max_count=3,
        )
        log.info("%s A=%s", tid, ans)
        log.info("  dist=%s", [a["value"] for a in acc])
        if rej:
            log.info("  rejected=%s", [(r["value"], r.get("gate_reason")) for r in rej])

        if len(acc) < 2:
            log.error("  FAIL need >=2 distractors")
            fail += 1
            continue

        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        for key in (
            "distractor_regen_exhausted",
            "distractor_regen_attempts",
            "distractor_regen_pending",
            "choices_complete",
        ):
            tags.pop(key, None)
        tags["smart_verify_status"] = tags.get("smart_verify_status") or "verified_match"
        tags["choices_complete"] = True
        tags["distractor_manual"] = "group_b_inequality"

        if args.dry_run:
            ok += 1
            continue

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET distractor_meta = cast(:dmeta AS jsonb),
                        tags = cast(:tags AS jsonb),
                        verification_status = 'verified'
                    WHERE id = :id
                """),
                {
                    "id": tid,
                    "dmeta": json.dumps(acc[:3], ensure_ascii=False),
                    "tags": json.dumps(tags, ensure_ascii=False),
                },
            )
        ok += 1

    log.info("Done: ok=%d fail=%d", ok, fail)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
