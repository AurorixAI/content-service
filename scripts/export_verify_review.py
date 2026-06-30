#!/usr/bin/env python3
"""
Export tasks needing human review (verify_conflict / verify_unresolved).

Usage:
  docker exec content-worker python /app/scripts/export_verify_review.py --class-level 8
  docker exec content-worker python /app/scripts/export_verify_review.py --grades 5-8 -o /tmp/review.json
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from src.core.config import get_settings


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--class-level", type=int)
    p.add_argument("--grades", type=str, help="e.g. 5-8")
    p.add_argument("-o", "--output", default="/tmp/verify_review.json")
    args = p.parse_args()

    if args.grades:
        a, b = args.grades.split("-", 1)
        levels = tuple(range(int(a), int(b) + 1))
    elif args.class_level:
        levels = (args.class_level,)
    else:
        p.error("Specify --class-level or --grades")

    level_sql = ", ".join(str(x) for x in levels)
    engine = create_engine(get_settings().database_url)
    sql = f"""
        SELECT tm.id, tb.class_level, tb.title, tm.answer_type,
               left(tm.question_text, 500) as question,
               tm.correct_answer,
               tm.tags->>'answer_previous' as answer_previous,
               tm.tags->>'answer_gemini_candidate' as gemini_flash,
               tm.tags->>'answer_gemini_pro_candidate' as gemini_pro,
               tm.tags->>'answer_verify_mode' as verify_mode,
               tm.tags->>'smart_verify_status' as smart_verify_status,
               tm.tags->>'sympy_compatible_string' as sympy_string,
               tm.tags->>'step_by_step_solution' as solution,
               tm.tags->>'answer_gemini_candidate' as gemini_candidate,
               tm.tags->>'answer_canonical_source' as canonical_source,
               tm.tags->>'answer_llm_prose' as llm_prose,
               tm.tags->>'self_consistency_votes' as consistency_votes,
               tm.tags->>'distractor_gate_rejected' as dist_rejected,
               COALESCE(tm.tags->>'verify_conflict', 'false') as conflict,
               COALESCE(tm.tags->>'verify_unresolved', 'false') as unresolved
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level IN ({level_sql})
          AND (
            COALESCE(tm.tags->>'verify_conflict', 'false') = 'true'
            OR COALESCE(tm.tags->>'verify_unresolved', 'false') = 'true'
            OR COALESCE(tm.tags->>'answer_mismatch', 'false') = 'true'
            OR COALESCE(tm.tags->>'smart_verify_status', '') IN (
              'needs_human_review', 'failed_at_llm', 'failed_at_sympy'
            )
          )
        ORDER BY tb.class_level, tm.id
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()

    out = []
    for r in rows:
        out.append({
            "id": r[0],
            "class_level": r[1],
            "textbook": r[2],
            "answer_type": r[3],
            "question": r[4],
            "stored_answer": r[5],
            "answer_previous": r[6],
            "gemini_flash": r[7],
            "gemini_pro": r[8],
            "verify_mode": r[9],
            "smart_verify_status": r[10],
            "sympy_string": r[11],
            "solution": r[12],
            "gemini_candidate": r[13],
            "canonical_source": r[14],
            "llm_prose": r[15],
            "consistency_votes": r[16],
            "distractor_gate_rejected": r[17],
            "verify_conflict": r[18] == "true",
            "verify_unresolved": r[19] == "true",
        })

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(out)} tasks to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
