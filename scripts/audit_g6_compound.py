#!/usr/bin/env python3
"""Audit G6 needs_compound_split — count + live re-detect."""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.compound_detect import detect_compound


def main() -> int:
    e = create_engine(get_settings().database_url)
    with e.connect() as c:
        n_status = c.execute(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6
                  AND tags->>'smart_verify_status' = 'needs_compound_split'
            """)
        ).scalar()
        n_tag = c.execute(
            text("""
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6
                  AND tags->>'needs_compound_split' = 'true'
            """)
        ).scalar()
        print(f"status=needs_compound_split: {n_status}")
        print(f"tag needs_compound_split=true: {n_tag}")

        print("\nby answer_type:")
        for row in c.execute(
            text("""
                SELECT tm.answer_type, count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6
                  AND tags->>'smart_verify_status' = 'needs_compound_split'
                GROUP BY 1 ORDER BY 2 DESC
            """)
        ):
            print(f"  {row[0]}: {row[1]}")

        print("\ncompound_pattern:")
        for row in c.execute(
            text("""
                SELECT coalesce(tags->>'compound_pattern', '(none)'), count(*)
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6
                  AND tags->>'smart_verify_status' = 'needs_compound_split'
                GROUP BY 1 ORDER BY 2 DESC
            """)
        ):
            print(f"  {row[0]}: {row[1]}")

        rows = c.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6
                  AND tags->>'smart_verify_status' = 'needs_compound_split'
                ORDER BY tm.id
            """)
        ).fetchall()

    real = atomic = 0
    fp_samples: list = []
    real_samples: list = []
    for tid, q, ans, atype, tags in rows:
        tags = dict(tags or {})
        cd = detect_compound(
            task_id=tid,
            question_text=q or "",
            correct_answer=ans or "",
            answer_type=atype or "",
            tags=tags,
        )
        if cd.should_split and cd.exam_unsafe:
            real += 1
            if len(real_samples) < 5:
                real_samples.append((tid, cd.pattern, cd.n_subitems, q, ans))
        else:
            atomic += 1
            if len(fp_samples) < 8:
                fp_samples.append((tid, tags.get("compound_pattern"), cd.pattern, (q or "")[:80]))

    print(f"\nLIVE re-detect on {len(rows)} tagged:")
    print(f"  still compound (need split): {real}")
    print(f"  atomic / false positive:     {atomic}")

    if fp_samples:
        print("\nFalse positive samples:")
        for s in fp_samples:
            print(f"  {s[0]} tag_pat={s[1]} live_pat={s[2]}")
            print(f"    Q: {s[3]}")

    if real_samples:
        print("\nReal compound samples:")
        for tid, pat, n, q, ans in real_samples:
            print(f"--- {tid} pattern={pat} subitems={n}")
            print((q or "")[:180])
            print(f"A: {(ans or '')[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
