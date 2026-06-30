#!/usr/bin/env python3
"""Promote pure-numeric expression answers to exact_number (G8)."""
from __future__ import annotations

import argparse
import logging
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import to_answer_latex

log = logging.getLogger("fix_g8_expression_exact_number")
logging.basicConfig(level=logging.INFO, format="%(message)s")

_NUM_RE = re.compile(r"^-?\d+([.,]\d+)?$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id-prefix", default="G8_%")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=5000)
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    updated = 0

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, correct_answer, answer_type
                FROM tasks_master
                WHERE id LIKE :prefix
                  AND answer_type = 'expression'
                  AND correct_answer ~ '^-?[0-9]+([.,][0-9]+)?$'
                ORDER BY id
                LIMIT :limit
            """),
            {"prefix": args.id_prefix, "limit": args.limit},
        ).fetchall()

    for tid, ans, _ in rows:
        ans = (ans or "").strip()
        if not _NUM_RE.match(ans):
            continue
        latex = to_answer_latex(ans, "exact_number") or ""
        log.info("%s expression → exact_number: %s", tid, ans)
        updated += 1
        if args.dry_run:
            continue
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET answer_type = 'exact_number',
                        correct_answer_latex = :latex,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": tid, "latex": latex},
            )

    log.info("Done: updated=%d dry_run=%s", updated, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
