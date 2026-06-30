#!/usr/bin/env python3
"""Grade quality dashboard — tasks, verify, distractors, LaTeX."""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int, required=True)
    args = ap.parse_args()
    level = args.class_level
    prefix = f"G{level}_"

    engine = create_engine(os.environ.get("DATABASE_URL") or __import__(
        "src.core.config", fromlist=["get_settings"]
    ).get_settings().database_url)

    q = text("""
        WITH g AS (
            SELECT tm.*
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = :level
        )
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE verification_status = 'verified') AS verified,
            count(*) FILTER (WHERE coalesce(correct_answer,'') != '') AS with_answer,
            count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]'::jsonb)) >= 2) AS dist_ge2,
            count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]'::jsonb)) < 2) AS dist_gaps,
            count(*) FILTER (WHERE coalesce(question_latex,'') != '') AS q_latex,
            count(*) FILTER (WHERE coalesce(correct_answer_latex,'') != '') AS ans_latex,
            count(*) FILTER (
                WHERE jsonb_array_length(COALESCE(distractor_meta,'[]'::jsonb)) >= 2
                  AND NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements(distractor_meta) d
                    WHERE coalesce(d->>'value_latex','') = ''
                  )
            ) AS dist_latex_full,
            count(*) FILTER (WHERE tags->>'smart_verify_status' LIKE 'failed%') AS verify_failed,
            count(*) FILTER (WHERE tags->>'smart_verify_status' = 'needs_human_review') AS human_review,
            count(*) FILTER (WHERE tags->>'generated_from_scratch' = 'true') AS from_scratch
        FROM g
    """)

    by_type = text("""
        SELECT answer_type, count(*) AS n
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = :level
        GROUP BY answer_type ORDER BY n DESC
    """)

    with engine.connect() as conn:
        r = conn.execute(q, {"level": level}).mappings().one()
        types = conn.execute(by_type, {"level": level}).fetchall()

    print(f"{'=' * 60}")
    print(f"GRADE {level}  (prefix {prefix})")
    print(f"{'=' * 60}")
    for k, v in r.items():
        pct = f" ({100 * v / r['total']:.1f}%)" if r["total"] and k != "total" else ""
        print(f"  {k:20} {v}{pct}")
    print("\nBy answer_type:")
    for row in types:
        print(f"  {row[0] or '?':20} {row[1]}")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
