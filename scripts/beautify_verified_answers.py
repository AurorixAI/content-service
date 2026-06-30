#!/usr/bin/env python3
"""Reformat verified answers from raw SymPy style to school notation."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import (
    answer_needs_school_format,
    beautify_answer_if_equivalent,
    to_answer_latex,
)

log = logging.getLogger(__name__)


def main() -> int:
    p = argparse.ArgumentParser(description="Beautify verified answers in DB")
    p.add_argument("--class-level", type=int, action="append", dest="levels")
    p.add_argument("--answer-type", type=str, default="expression")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--backfill-latex", action="store_true",
                   help="Fill correct_answer_latex when empty (no answer rewrite)")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing correct_answer_latex")
    p.add_argument("--limit", type=int, default=5000)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    levels = args.levels or [8]
    level_sql = ", ".join(str(x) for x in levels)
    engine = create_engine(get_settings().database_url)

    sql = f"""
        SELECT tm.id, tm.correct_answer, tm.answer_type, tm.tags,
               COALESCE(tm.correct_answer_latex, '') AS answer_latex
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level IN ({level_sql})
          AND tm.answer_type = :atype
          AND COALESCE(tm.tags->>'smart_verify_status', '') IN (
            'verified_match', 'verified_corrected'
          )
        ORDER BY tm.id
        LIMIT :limit
    """
    updated = 0
    scanned = 0
    with engine.connect() as conn:
        rows = conn.execute(
            text(sql),
            {"atype": args.answer_type, "limit": args.limit},
        ).fetchall()
        for tid, ans, atype, tags_raw, answer_latex in rows:
            scanned += 1
            ans = (ans or "").strip()
            answer_latex = (answer_latex or "").strip()

            if args.backfill_latex:
                if answer_latex and not args.force:
                    continue
                latex = to_answer_latex(ans, atype)
                if not latex:
                    continue
                log.info("%s backfill latex: %s", tid, latex[:90])
                updated += 1
                if args.dry_run:
                    continue
                tags = tags_raw if isinstance(tags_raw, dict) else json.loads(tags_raw or "{}")
                with engine.begin() as w:
                    w.execute(
                        text("""
                            UPDATE tasks_master
                            SET correct_answer_latex = :latex, updated_at = NOW()
                            WHERE id = :id
                        """),
                        {"id": tid, "latex": latex},
                    )
                continue

            if not answer_needs_school_format(ans, atype):
                continue
            pretty = beautify_answer_if_equivalent(ans, atype)
            if pretty == ans and not answer_needs_school_format(ans, atype):
                latex = to_answer_latex(ans, atype)
                if latex == ans:
                    continue
            else:
                latex = to_answer_latex(pretty, atype)
            if pretty == ans and latex == ans:
                continue
            log.info("%s\n  was: %s\n  now: %s\n  latex: %s", tid, ans[:90], pretty[:90], latex[:90])
            updated += 1
            if args.dry_run:
                continue
            tags = tags_raw if isinstance(tags_raw, dict) else json.loads(tags_raw or "{}")
            tags["answer_beautified"] = True
            with engine.begin() as w:
                w.execute(
                    text("""
                        UPDATE tasks_master
                        SET correct_answer = :ans,
                            correct_answer_latex = :latex,
                            tags = cast(:tags as jsonb),
                            updated_at = NOW()
                        WHERE id = :id
                    """),
                    {
                        "id": tid,
                        "ans": pretty,
                        "latex": latex,
                        "tags": json.dumps(tags, ensure_ascii=False),
                    },
                )

    log.info("scanned=%s updated=%s dry_run=%s", scanned, updated, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
