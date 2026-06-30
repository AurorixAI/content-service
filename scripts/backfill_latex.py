#!/usr/bin/env python3
"""LaTeX backfill: question_latex, correct_answer_latex, distractor value_latex."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import (
    enrich_distractor_latex,
    to_answer_latex,
    to_question_latex,
)

log = logging.getLogger("backfill_latex")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def should_backfill_answer(ans: str, atype: str, cal: str) -> bool:
    return bool((ans or "").strip()) and not (cal or "").strip()


def should_backfill_distractor(value: str, atype: str) -> bool:
    return bool((value or "").strip())


def task_filter_sql(class_level: int | None, prefix: str | None) -> tuple[str, dict]:
    if prefix:
        return "id LIKE :prefix", {"prefix": prefix}
    if class_level is not None:
        return (
            """id IN (
                SELECT tm.id FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
            )""",
            {"level": class_level},
        )
    return "TRUE", {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int, help="Grade filter via textbooks (e.g. 7, 8)")
    ap.add_argument("--prefix", help="Task id prefix (e.g. G8_%%, G7_TB_%%)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--questions-only", action="store_true")
    ap.add_argument("--answers-only", action="store_true")
    ap.add_argument("--distractors-only", action="store_true")
    ap.add_argument(
        "--upgrade-questions",
        action="store_true",
        help="Re-run to_question_latex when output differs (math wrap pass)",
    )
    args = ap.parse_args()

    if not args.prefix and args.class_level is None:
        ap.error("Provide --class-level or --prefix")

    do_q = not args.answers_only and not args.distractors_only
    do_a = not args.questions_only and not args.distractors_only
    do_d = not args.questions_only and not args.answers_only

    where_sql, filter_params = task_filter_sql(args.class_level, args.prefix)
    engine = create_engine(get_settings().database_url)
    q_up = a_up = d_up = 0

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, answer_type, question_text,
                       COALESCE(question_latex, '') AS ql,
                       correct_answer,
                       COALESCE(correct_answer_latex, '') AS cal,
                       distractor_meta
                FROM tasks_master
                WHERE {where_sql}
                ORDER BY id
            """),
            filter_params,
        ).mappings().all()

    log.info("Tasks to scan: %d", len(rows))

    for row in rows:
        tid = row["id"]
        atype = row["answer_type"] or ""
        qt = (row["question_text"] or "").strip()
        ql = (row["ql"] or "").strip()
        ans = (row["correct_answer"] or "").strip()
        cal = (row["cal"] or "").strip()
        dmeta = list(row["distractor_meta"] or [])

        new_ql = ql
        if do_q and qt:
            candidate = to_question_latex(qt)
            if candidate and (
                (not ql and candidate)
                or (args.upgrade_questions and candidate != ql)
            ):
                new_ql = candidate
                log.info("%s question latex", tid)
                q_up += 1

        new_cal = cal
        if do_a and should_backfill_answer(ans, atype, cal):
            candidate = to_answer_latex(ans, atype)
            if candidate and candidate != cal:
                new_cal = candidate
                log.info("%s answer latex: %s", tid, new_cal[:90])
                a_up += 1

        new_dmeta = dmeta
        if do_d and dmeta:
            needs = any(
                isinstance(d, dict)
                and (d.get("value") or "").strip()
                and not (d.get("value_latex") or "").strip()
                and should_backfill_distractor(str(d.get("value")), atype)
                for d in dmeta
            )
            if needs:
                enriched = enrich_distractor_latex(dmeta, atype)
                if json.dumps(enriched, ensure_ascii=False) != json.dumps(dmeta, ensure_ascii=False):
                    n = sum(
                        1
                        for a, b in zip(dmeta, enriched)
                        if isinstance(a, dict)
                        and isinstance(b, dict)
                        and not (a.get("value_latex") or "").strip()
                        and (b.get("value_latex") or "").strip()
                    )
                    log.info("%s distractor latex: +%d", tid, n)
                    new_dmeta = enriched
                    d_up += 1

        if args.dry_run:
            continue

        if new_ql != ql or new_cal != cal or new_dmeta is not dmeta:
            sets: list[str] = []
            params: dict = {"id": tid}
            if new_dmeta is not dmeta:
                params["dmeta"] = json.dumps(new_dmeta, ensure_ascii=False)
                sets.append("distractor_meta = cast(:dmeta AS jsonb)")
            if new_ql != ql:
                params["ql"] = new_ql
                sets.append("question_latex = :ql")
            if new_cal != cal:
                params["cal"] = new_cal
                sets.append("correct_answer_latex = :cal")
            sets.append("updated_at = NOW()")
            with engine.begin() as conn:
                conn.execute(
                    text(f"UPDATE tasks_master SET {', '.join(sets)} WHERE id = :id"),
                    params,
                )

    log.info("Done: questions=%d answers=%d distractor_tasks=%d dry=%s", q_up, a_up, d_up, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
