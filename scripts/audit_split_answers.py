#!/usr/bin/env python3
"""Audit split children answers — read-only."""
from __future__ import annotations

import re
import sys
from collections import Counter

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from src.core.config import get_settings

import importlib.util
_spec = importlib.util.spec_from_file_location("split_mod", "/app/scripts/split_compound_tasks.py")
_split = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_split)
_parse_question = _split._parse_question
_question_uses_letters = _split._question_uses_letters

TB = "b8f4a2c1-3d5e-4f60-9182-3456789abcde"


def main() -> int:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as c:
        children = c.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer,
                       tm.tags->>'split_from' AS parent_id, tm.answer_type
                FROM tasks_master tm
                JOIN textbook_toc t ON t.id = tm.toc_id
                WHERE t.textbook_id = CAST(:tb AS UUID)
                  AND tm.tags ? 'split_from'
                ORDER BY parent_id, tm.id
            """),
            {"tb": TB},
        ).mappings().all()

    by_parent: dict[str, list[dict]] = {}
    for ch in children:
        by_parent.setdefault(ch["parent_id"], []).append(dict(ch))

    total = len(children)
    empty = [c for c in children if not (c["correct_answer"] or "").strip()]
    marker = [
        c for c in children
        if re.match(r"^(\d+|[абвг])\)\s", (c["correct_answer"] or "").strip(), re.I)
    ]

    partial = []
    for pid, kids in by_parent.items():
        n = len(kids)
        filled = sum(1 for k in kids if (k["correct_answer"] or "").strip())
        if filled < n:
            partial.append((pid, n, filled, n - filled))

    partial.sort(key=lambda x: -x[3])

    print("=== SPLIT ANSWER AUDIT (Makarychev G8) ===")
    print(f"children: {total}")
    print(f"empty: {len(empty)} ({100 * len(empty) / max(total, 1):.1f}%)")
    print(f"marker prefix leak (а)/1)): {len(marker)}")
    print(f"parents partial: {len(partial)} / {len(by_parent)}")
    print(f"empty by type: {dict(Counter(c['answer_type'] for c in empty))}")

    print("\n--- GOOD example G8_TB_21_545 (roots а)б)в)г) — NOT split, kept compound) ---")
    with engine.connect() as c:
        row = c.execute(
            text("SELECT id, correct_answer FROM tasks_master WHERE id='G8_TB_21_545'")
        ).fetchone()
    if row:
        print("  still exists as single task (MCQ/укажите guard)")
    else:
        print("  (not in DB as single — may have been split or renamed)")

    print("\n--- GOOD numeric children G8_TB_2_* ---")
    for pid in sorted(by_parent):
        if pid.startswith("G8_TB_2_") and pid.endswith("_42"):
            for k in by_parent[pid][:3]:
                print(f"  {k['id']}: {k['correct_answer'][:60]}")
            break

    print("\n--- GOOD letter children (sample) ---")
    shown = 0
    for c in children:
        if c["parent_id"] == "G8_TB_42_1078":
            print(f"  {c['id']}: {(c['correct_answer'] or '')[:70]}")
            shown += 1
        if shown >= 4:
            break

    print("\n--- WORST partial (no re-OCR, parent deleted) ---")
    for pid, n, filled, miss in partial[:10]:
        print(f"\n{pid}: {filled}/{n} ({miss} empty)")
        for k in by_parent[pid]:
            a = (k["correct_answer"] or "").strip() or "(empty)"
            print(f"  {k['id']}: {a[:80]}")

    if marker:
        print("\n--- marker leak ---")
        for c in marker[:5]:
            print(f"  {c['id']}: {c['correct_answer'][:80]!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
