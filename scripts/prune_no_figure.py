#!/usr/bin/env python3
"""Delete tasks that require an external figure but have no image attached."""
from __future__ import annotations

import argparse
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings

NEEDS_EXT_FIG = re.compile(
    r"по рисунку|на рисунке|рисунке\s+\d+|рис\.\s*\d+|изображ[её]нн[а-я]+ на рис|"
    r"пользуясь графиком[^,]*рисунке|используя график[^.]*рис\.|"
    r"рисунки к задаче отсутств|отсутствуют в тексте|"
    r"изображенного на рисунке|"
    r"(?<![а-яё])черт[её]ж(?![а-яё])",  # not «чертежей» / «на чертежах»
    re.I,
)

# Explicit deletes: broken compound parents (G7), cross-page figure refs (G8/G6)
EXTRA_DELETE_BY_LEVEL: dict[int, frozenset[str]] = {
    6: frozenset({
        "G6_TB_6_211",
        "G6_TB_37_1365",
    }),
    7: frozenset({
        "G7_ALG_39_60",
        "G7_ALG_39_49",
    }),
    8: frozenset({
        "G8_TB_42_1082",
        "G8_TB_47_1166.3",
        "G8_TB_47_1167",
    }),
}


def find_candidates(engine, class_level: int) -> list[tuple[str, str]]:
    extra = EXTRA_DELETE_BY_LEVEL.get(class_level, frozenset())
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.question_image_url,
                       (SELECT COUNT(*) FROM task_figure_refs tfr
                        WHERE tfr.task_id = tm.id) AS fig_refs
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                ORDER BY tm.id
            """),
            {"level": class_level},
        ).all()

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tid, question, image_url, fig_refs in rows:
        q = question or ""
        no_img = not image_url and (fig_refs or 0) == 0
        if tid in extra:
            out.append((tid, q[:100]))
            seen.add(tid)
            continue
        if no_img and NEEDS_EXT_FIG.search(q) and tid not in seen:
            out.append((tid, q[:100]))
            seen.add(tid)
    return out


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
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int, required=True, choices=(6, 7, 8))
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    dry_run = not args.execute

    engine = create_engine(get_settings().database_url)
    candidates = find_candidates(engine, args.class_level)
    ids = [c[0] for c in candidates]

    print(f"G{args.class_level} prune: {len(ids)} tasks to delete")
    for tid, preview in candidates:
        print(f"  {tid} | {preview}")

    if dry_run:
        print("\n[DRY RUN] pass --execute to delete")
        return 0

    n = delete_tasks(engine, ids)
    print(f"\nDeleted {n} tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
