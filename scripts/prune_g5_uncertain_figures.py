#!/usr/bin/env python3
"""Delete G5 required-figure tasks without 100% verified binding."""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings

KEEP_100 = frozenset({
    "G5_TB_3_45",
    "G5_TB_52_1238",
})

DELETE_UNCERTAIN = frozenset({
    "G5_TB_3_46",
    "G5_TB_6_86",
    "G5_TB_42_42",
    "G5_TB_42_59",
    "G5_TB_46_987",
    "G5_TB_52_1236",
    "G5_TB_55_1294",
})


def delete_tasks(engine, task_ids: list[str]) -> int:
    if not task_ids:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM task_figure_refs WHERE task_id = ANY(:ids)"),
            {"ids": task_ids},
        )
        conn.execute(
            text("DELETE FROM textbook_tasks WHERE task_id = ANY(:ids)"),
            {"ids": task_ids},
        )
        n = conn.execute(
            text("DELETE FROM tasks_master WHERE id = ANY(:ids) RETURNING id"),
            {"ids": task_ids},
        ).rowcount
        conn.execute(text("""
            UPDATE textbooks tb
            SET tasks_extracted = sub.cnt
            FROM (
              SELECT tt.textbook_id, COUNT(*) AS cnt
              FROM textbook_tasks tt
              JOIN textbooks t ON t.textbook_id = tt.textbook_id
              WHERE t.class_level = 5
              GROUP BY tt.textbook_id
            ) sub
            WHERE tb.textbook_id = sub.textbook_id AND tb.class_level = 5
        """))
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    ids = sorted(DELETE_UNCERTAIN)
    print(f"Delete (no 100% binding): {len(ids)}")
    for tid in ids:
        print(f"  {tid}")
    print(f"\nKeep (verified): {sorted(KEEP_100)}")

    if not args.execute:
        print("\n[DRY RUN] pass --execute")
        return 0

    engine = create_engine(get_settings().database_url)
    n = delete_tasks(engine, ids)
    print(f"\nDeleted: {n}")

    with engine.connect() as c:
        total = c.execute(text("""
            SELECT COUNT(*) FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = 5
        """)).scalar()
        for tid in KEEP_100:
            ok = c.execute(text("""
                SELECT EXISTS (SELECT 1 FROM tasks_master WHERE id = :id)
                AND (SELECT COUNT(*) FROM task_figure_refs WHERE task_id = :id) > 0
            """), {"id": tid}).scalar()
            print(f"  {tid}: {'OK' if ok else 'MISSING'}")
    print(f"G5 total: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
