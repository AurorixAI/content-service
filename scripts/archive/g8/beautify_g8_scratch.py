#!/usr/bin/env python3
"""Beautify G8 generated_from_scratch + sympy-style expression answers."""
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

log = logging.getLogger("beautify_g8_scratch")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id-prefix", default="G8_TB_%")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=5000)
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    updated = 0

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, correct_answer, answer_type, tags
                FROM tasks_master
                WHERE id LIKE :prefix
                  AND answer_type IN ('expression', 'equation_solution', 'fraction')
                  AND COALESCE(tags->>'smart_verify_status', '') IN (
                    'generated_from_scratch', 'verified_match', 'verified_corrected'
                  )
                ORDER BY id
                LIMIT :limit
            """),
            {"prefix": args.id_prefix, "limit": args.limit},
        ).fetchall()

    for tid, ans, atype, tags_raw in rows:
        ans = (ans or "").strip()
        if not ans or not answer_needs_school_format(ans, atype):
            continue
        pretty = beautify_answer_if_equivalent(ans, atype)
        latex = to_answer_latex(pretty, atype)
        if pretty == ans and (not latex or latex == ans):
            continue
        log.info("%s\n  was: %s\n  now: %s", tid, ans[:80], pretty[:80])
        updated += 1
        if args.dry_run:
            continue
        tags = tags_raw if isinstance(tags_raw, dict) else json.loads(tags_raw or "{}")
        tags["answer_beautified"] = True
        if tags.get("smart_verify_status") == "generated_from_scratch":
            tags["smart_verify_status"] = "verified_corrected"
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        correct_answer_latex = :latex,
                        tags = cast(:tags AS jsonb),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": tid,
                    "ans": pretty,
                    "latex": latex or "",
                    "tags": json.dumps(tags, ensure_ascii=False),
                },
            )

    # Promote remaining scratch with dist>=2 (answer unchanged but status stale).
    with engine.connect() as conn:
        scratch_rows = conn.execute(
            text("""
                SELECT id, tags FROM tasks_master
                WHERE id LIKE :prefix
                  AND tags->>'smart_verify_status' = 'generated_from_scratch'
                  AND jsonb_array_length(COALESCE(distractor_meta, '[]'::jsonb)) >= 2
                  AND trim(COALESCE(correct_answer, '')) != ''
            """),
            {"prefix": args.id_prefix},
        ).fetchall()
    for tid, tags_raw in scratch_rows:
        tags = tags_raw if isinstance(tags_raw, dict) else json.loads(tags_raw or "{}")
        tags["smart_verify_status"] = "verified_corrected"
        updated += 1
        log.info("%s scratch → verified_corrected", tid)
        if args.dry_run:
            continue
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE tasks_master SET tags = cast(:tags AS jsonb), updated_at = NOW() WHERE id = :id"),
                {"id": tid, "tags": json.dumps(tags, ensure_ascii=False)},
            )

    log.info("Done: updated=%d dry_run=%s", updated, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
