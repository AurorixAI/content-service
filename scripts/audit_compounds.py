#!/usr/bin/env python3
"""
Audit unsplit compound tasks across grades.

Usage:
  python scripts/audit_compounds.py
  python scripts/audit_compounds.py --class-level 8
  python scripts/audit_compounds.py --tag  # write needs_compound_split tags
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.compound_detect import apply_compound_tags, detect_compound

log = logging.getLogger("audit_compounds")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit unsplit compound tasks")
    ap.add_argument("--class-level", type=int, default=None)
    ap.add_argument("--tag", action="store_true", help="Tag needs_compound_split in DB")
    ap.add_argument("--limit", type=int, default=0, help="Max examples per bucket")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    level_filter = ""
    params: dict = {}
    if args.class_level:
        level_filter = "AND tb.class_level = :level"
        params["level"] = args.class_level

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
                       tm.tags, tb.class_level,
                       tt.exercise_number
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                LEFT JOIN textbook_tasks tt ON tt.task_id = tm.id
                    AND tt.textbook_id = tb.textbook_id
                WHERE tm.answer_type NOT IN ('text', 'open_text', 'coordinate')
                  {level_filter}
                ORDER BY tb.class_level, tm.id
            """),
            params,
        ).mappings().all()

    from collections import Counter, defaultdict

    by_level: dict[int, Counter] = defaultdict(Counter)
    by_pattern: Counter = Counter()
    examples: dict[str, list] = defaultdict(list)
    tagged = 0

    for row in rows:
        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        cd = detect_compound(
            task_id=row["id"],
            question_text=row["question_text"] or "",
            correct_answer=row["correct_answer"] or "",
            answer_type=row["answer_type"] or "",
            tags=tags,
            exercise_number=str(row["exercise_number"] or ""),
        )
        lvl = int(row["class_level"])
        if cd.is_split_child and not cd.nested_compound:
            by_level[lvl]["split_child_ok"] += 1
            continue
        if cd.is_mcq:
            by_level[lvl]["mcq_ok"] += 1
            continue
        if cd.should_split:
            bucket = "needs_split_nested" if cd.nested_compound else "needs_split_top"
            by_level[lvl][bucket] += 1
            by_level[lvl]["needs_split"] += 1
            by_level[lvl][f"pat_{cd.pattern}"] += 1
            by_pattern[cd.pattern] += 1
            if len(examples[cd.pattern]) < (args.limit or 5):
                examples[cd.pattern].append(
                    (row["id"], cd.n_subitems, (row["correct_answer"] or "")[:55])
                )
            if args.tag:
                new_tags = apply_compound_tags(tags, cd)
                new_tags["smart_verify_status"] = tags.get("smart_verify_status") or "pending"
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE tasks_master
                            SET tags = cast(:tags as jsonb)
                            WHERE id = :id
                        """),
                        {
                            "id": row["id"],
                            "tags": json.dumps(new_tags, ensure_ascii=False),
                        },
                    )
                tagged += 1
        else:
            by_level[lvl]["atomic_ok"] += 1

    print("=" * 60)
    print("COMPOUND AUDIT")
    if args.class_level:
        print(f"Class level: {args.class_level}")
    print("=" * 60)
    total_split = sum(c["needs_split"] for c in by_level.values())
    total_nested = sum(c["needs_split_nested"] for c in by_level.values())
    total_top = sum(c["needs_split_top"] for c in by_level.values())
    total_children = sum(c["split_child_ok"] for c in by_level.values())
    print(f"Total tasks scanned: {len(rows)}")
    print(f"Split children (atomic OK): {total_children}")
    print(f"NEEDS SPLIT (exam-unsafe): {total_split}")
    print(f"  top-level (never split): {total_top}")
    print(f"  nested (split_from + still compound): {total_nested}")
    print()
    print("By class level:")
    for lvl in sorted(by_level):
        c = by_level[lvl]
        print(
            f"  G{lvl}: needs_split={c['needs_split']} "
            f"(top={c['needs_split_top']} nested={c['needs_split_nested']})  "
            f"split_child_ok={c['split_child_ok']}  "
            f"atomic={c['atomic_ok']}  mcq={c['mcq_ok']}"
        )
        for k, v in sorted(c.items()):
            if k.startswith("pat_"):
                print(f"       {k[4:]}: {v}")
    print()
    print("Patterns (needs split):")
    for pat, n in by_pattern.most_common():
        print(f"  {pat}: {n}")
        for tid, nsub, ans in examples.get(pat, []):
            print(f"    {tid} ({nsub} parts) A={ans}")
    if args.tag:
        print(f"\nTagged {tagged} tasks with needs_compound_split=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
