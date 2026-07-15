#!/usr/bin/env python3
"""Audit verified tasks: local SymPy answer vs stored (no textbook trust)."""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.arith_from_question import (
    compute_answer_from_question,
    is_high_confidence_arithmetic,
    stored_matches_computed,
)


def fetch_tasks(engine, levels: tuple[int, ...]) -> list[dict]:
    level_sql = ", ".join(str(x) for x in levels)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
                       tm.tags->>'answer_source' AS answer_source,
                       tm.tags->>'split_from' AS split_from
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level IN ({level_sql})
                  AND tm.verification_status = 'verified'
                ORDER BY tm.id
                """
            )
        ).mappings().all()
    return [dict(r) for r in rows]


def audit(levels: tuple[int, ...], *, limit: int = 0) -> dict:
    engine = create_engine(get_settings().database_url)
    rows = fetch_tasks(engine, levels)
    stats = {
        "levels": list(levels),
        "total": len(rows),
        "computable": 0,
        "match": 0,
        "mismatch": 0,
        "textbook_source": 0,
        "split_children": 0,
    }
    mismatches: list[dict] = []

    for row in rows:
        if row.get("split_from"):
            stats["split_children"] += 1
        if row.get("answer_source") == "textbook":
            stats["textbook_source"] += 1

        q = row["question_text"] or ""
        stored = (row["correct_answer"] or "").strip()
        at = row["answer_type"] or "text"

        if not is_high_confidence_arithmetic(q):
            continue

        computed = compute_answer_from_question(q)
        if not computed:
            continue
        stats["computable"] += 1

        check = stored_matches_computed(q, stored, answer_type=at)
        if check is True:
            stats["match"] += 1
            continue
        if check is False:
            stats["mismatch"] += 1
            mismatches.append(
                {
                    "id": row["id"],
                    "stored": stored[:120],
                    "computed": computed[:120],
                    "split_from": row.get("split_from"),
                    "answer_source": row.get("answer_source"),
                }
            )
            if limit and len(mismatches) >= limit:
                break

    stats["mismatches"] = mismatches
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grades", default="5-8", help="e.g. 5 or 5-8")
    ap.add_argument("--limit", type=int, default=0, help="max mismatch samples")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if "-" in args.grades:
        a, b = args.grades.split("-", 1)
        levels = tuple(range(int(a), int(b) + 1))
    else:
        levels = (int(args.grades),)

    result = audit(levels, limit=args.limit)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"G{result['levels']}: total={result['total']} "
            f"computable={result['computable']} match={result['match']} "
            f"mismatch={result['mismatch']} textbook_source={result['textbook_source']}"
        )
        for m in result["mismatches"][:50]:
            print(f"  {m['id']}: stored={m['stored']!r} → computed={m['computed']!r}")
        if len(result["mismatches"]) > 50:
            print(f"  ... +{len(result['mismatches']) - 50} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
