#!/usr/bin/env python3
"""Breakdown of G6 trust-bypass tasks (fix_g6_failed + fix_g6_human_review)."""
from __future__ import annotations

import sys
from collections import Counter

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings


def main() -> int:
    e = create_engine(get_settings().database_url)
    with e.connect() as c:
        print("=" * 60)
        print("FIX_G6_FAILED — trust bypass")
        print("=" * 60)
        rows = c.execute(
            text("""
                SELECT tm.id, tm.answer_type,
                       left(tm.correct_answer, 55) AS ans
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6 AND tm.tags->>'fix_g6_failed' = 'true'
                ORDER BY tm.answer_type, tm.id
            """)
        ).mappings().all()
        print("total", len(rows))
        for k, v in Counter(r["answer_type"] for r in rows).most_common():
            print(f"  {v:3d}  {k}")
        print("\nexamples:")
        for r in rows[:10]:
            print(f"  {r['id']} [{r['answer_type']}] {r['ans']}")

        print("\n" + "=" * 60)
        print("FIX_G6_HUMAN_REVIEW — trust bypass")
        print("=" * 60)
        rows2 = c.execute(
            text("""
                SELECT tm.id, tm.answer_type,
                       tm.tags->>'split_from' AS split_from,
                       left(tm.correct_answer, 55) AS ans
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6 AND tm.tags->>'fix_g6_human_review' = 'true'
                ORDER BY tm.id
            """)
        ).mappings().all()
        print("total", len(rows2))
        print("split children:", sum(1 for r in rows2 if r["split_from"]))
        for k, v in Counter(r["answer_type"] for r in rows2).most_common():
            print(f"  {v:3d}  {k}")
        print("\nexamples:")
        for r in rows2[:10]:
            sf = f" ←{r['split_from']}" if r["split_from"] else ""
            print(f"  {r['id']} [{r['answer_type']}]{sf} {r['ans']}")

        both = c.execute(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6
                  AND tm.tags->>'fix_g6_failed' = 'true'
                  AND tm.tags->>'fix_g6_human_review' = 'true'
            """)
        ).scalar()
        print("\noverlap (both tags):", both)
        print("sum unique bypass:", len(rows) + len(rows2) - both)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
