#!/usr/bin/env python3
"""Dump all G6 tasks needing review: MATH_FAIL, consensus_corrected, human_review."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from scripts.audit_g6_quality_honest import validate_any


def main() -> int:
    e = create_engine(get_settings().database_url)
    out: dict[str, list] = {"math_fail": [], "consensus": [], "human": []}
    with e.connect() as c:
        rows = c.execute(
            text(
                """
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6 AND tm.verification_status = 'verified'
                  AND (tm.tags->>'fix_g6_reverified' = 'true'
                       OR tm.tags->>'fix_g6_human_triage' IS NOT NULL)
                """
            )
        ).mappings().all()
        for r in rows:
            tags = r["tags"] or {}
            route = tags.get("fix_g6_human_triage") or tags.get("fix_g6_reverify_route") or "?"
            v = validate_any(r["question_text"], r["correct_answer"], r["answer_type"] or "text")
            rec = {
                "id": r["id"],
                "q": r["question_text"],
                "a": r["correct_answer"],
                "prev": tags.get("answer_previous"),
                "type": r["answer_type"],
                "route": route,
            }
            if v == "MATH_FAIL":
                out["math_fail"].append(rec)
            if route == "consensus_corrected":
                out["consensus"].append(rec)

        hrows = c.execute(
            text(
                """
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6
                  AND tm.tags->>'smart_verify_status' = 'needs_human_review'
                """
            )
        ).mappings().all()
        for r in hrows:
            tags = r["tags"] or {}
            out["human"].append(
                {
                    "id": r["id"],
                    "q": r["question_text"],
                    "a": r["correct_answer"],
                    "type": r["answer_type"],
                    "llm": tags.get("fix_g6_human_llm_answers") or tags.get("smart_verify_llm_answer"),
                }
            )

    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
