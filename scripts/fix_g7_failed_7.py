#!/usr/bin/env python3
"""Fix 7 remaining G7 verify failures and prep for Smart Verify re-run."""
from __future__ import annotations

import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.smart_verify_common import clear_stale_verify_flags

log = logging.getLogger("fix_g7_failed_7")
logging.basicConfig(level=logging.INFO, format="%(message)s")

FAILED_7: dict[str, dict] = {
    "G7_ALG_23_8.2": {
        "answer": "2(a-b)/(40a^4b^2); 25a^3/(40a^4b^2); 16a^2b/(40a^4b^2)",
    },
    "G7_ALG_23_8.4": {
        "answer": "6ab^3/(12a^3b^2); 2ab/(12a^3b^2); 5/(12a^3b^2)",
    },
    "G7_ALG_34_1.3": {"answer": "x = 2y + 4"},
    "G7_ALG_6_6.1": {"answer": "1,7·10^1", "answer_type": "text"},
    "G7_ALG_9_9.4": {"answer": "2x^6y^3; -8192"},
    "G7_TB_43_1095.1": {"answer": "(7,6; 2,8)"},
    "G7_TB_44_1107.2": {"answer": "a = -3, b = 1"},
}

TASK_IDS = tuple(FAILED_7.keys())


def _tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(raw or "{}")


def _clear_retry(tags: dict) -> None:
    for key in (
        "distractor_regen_exhausted",
        "distractor_regen_attempts",
        "distractor_regen_pending",
        "smart_verify_retry_exhausted",
        "smart_verify_retry_count",
        "smart_verify_error",
        "fix_g7_reprocess_failed",
        "fix_g7_reprocess_failed2",
        "fix_g7_reprocess_human",
    ):
        tags.pop(key, None)


def main() -> int:
    engine = create_engine(get_settings().database_url)
    with engine.begin() as conn:
        for tid, spec in FAILED_7.items():
            row = conn.execute(
                text(
                    "SELECT correct_answer, answer_type, tags FROM tasks_master WHERE id = :id"
                ),
                {"id": tid},
            ).mappings().first()
            if not row:
                log.warning("MISSING %s", tid)
                continue
            answer = spec.get("answer", row["correct_answer"])
            atype = spec.get("answer_type", row["answer_type"])
            tags = _tags(row["tags"])
            _clear_retry(tags)
            clear_stale_verify_flags(tags)
            log.info("FIX %s → %s", tid, answer[:70])
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        answer_type = :atype,
                        tags = cast(:tags AS jsonb),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": tid,
                    "ans": answer,
                    "atype": atype,
                    "tags": json.dumps(tags, ensure_ascii=False),
                },
            )
    log.info("Fixed %d tasks", len(FAILED_7))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
