#!/usr/bin/env python3
"""Analyze G7 human_review tail (45 tasks)."""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings


def main() -> int:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.answer_type, tm.correct_answer,
                       tm.tags->>'smart_verify_error' as err,
                       tm.tags->>'human_reprocess_status' as hrs,
                       COALESCE(tm.tags->>'human_reprocess_exhausted', 'false') as ex,
                       tm.tags->>'ai_answer' as ai_ans,
                       LEFT(tm.question_text, 120) as q
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 7
                  AND tm.tags->>'smart_verify_status' = 'needs_human_review'
                ORDER BY tm.answer_type, tm.id
            """),
        ).all()
    print("TOTAL", len(rows))
    for r in rows:
        print("---")
        print(r[0], r[1], f"ex={r[5]}", f"hrs={r[4]}")
        print("ANS:", r[2])
        print("AI:", r[6])
        print("ERR:", r[3])
        print("Q:", r[7])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
