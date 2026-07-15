#!/usr/bin/env python3
"""Persist G5 LLM mismatch re-audit trail + curated verdicts on tasks."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings

# 8 cases where textbook/OCR was wrong (already applied in fix_g5_human_review).
MANUAL_FIXED = {
    "G5_TB_13_245": "llm_right_math",
    "G5_TB_21_844": "llm_right_math",
    "G5_TB_25_987": "llm_right_math",
    "G5_TB_4_66": "llm_right_logic",
    "G5_TB_10_386.2": "llm_right_math",
    "G5_TB_41_726": "llm_right_content",
    "G5_TB_44_1718.4": "recalc_right",
    "G5_TB_55_1292": "llm_more_complete",
}

# Fresh Gemini re-audit 2026-07-07 (/tmp/g5_llm_mismatch_audit.json)
CURATED: dict[str, str] = {
    "G5_TB_67_1642": "tb_right_mcq",  # 4+3=7 decimal places → В
    "G5_TB_25_430": "tb_right_method",  # метод при отсутствии рисунка
    "G5_TB_3_45": "tb_right_method",
    "G5_TB_55_1303": "tb_right_method",
    "G5_TB_5_78": "tb_right_complete",  # TB полнее (округление)
    "G5_TB_9_334": "tb_right_complete",  # TB сохраняет пояснение m=6,n=9
}


def main() -> int:
    engine = create_engine(get_settings().database_url)
    with open("/tmp/g5_llm_mismatch_audit.json", encoding="utf-8") as f:
        audit = {r["id"]: r for r in json.load(f)}

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 5
                  AND (
                    tm.tags->>'fix_g5_human_review' = 'trust_textbook'
                    OR tm.tags->>'answer_corrected_manual' = 'true'
                  )
                ORDER BY tm.id
            """)
        ).all()

    updated = 0
    with engine.begin() as conn:
        for row in rows:
            tid = row.id
            tags = dict(row.tags or {})
            a = audit.get(tid)
            if tid in MANUAL_FIXED:
                verdict = f"fixed_{MANUAL_FIXED[tid]}"
                llm = (a or {}).get("llm", "")
            elif tid in CURATED:
                verdict = CURATED[tid]
                llm = (a or {}).get("llm", "")
            elif a:
                v = a.get("verdict", "")
                if v == "equivalent" or v == "keep_tb":
                    verdict = "confirmed_equivalent"
                elif v.startswith("review_"):
                    verdict = "confirmed_tb_after_review"
                else:
                    verdict = v
                llm = a.get("llm", "")
            else:
                continue

            tags["llm_mismatch_reaudit"] = verdict
            tags["answer_llm_reaudit"] = (llm or "")[:500]
            if a and a.get("confidence"):
                tags["text_reaudit_confidence"] = a["confidence"]
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET tags = cast(:tags AS jsonb)
                    WHERE id = :id
                """),
                {"id": tid, "tags": json.dumps(tags, ensure_ascii=False)},
            )
            updated += 1

    print(f"Tagged {updated} tasks with llm_mismatch_reaudit trail")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
