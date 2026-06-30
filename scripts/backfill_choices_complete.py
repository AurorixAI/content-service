#!/usr/bin/env python3
"""
Backfill choices_complete for verified G8 tasks that already have 3 valid distractors.

Root cause: apply_distractors skipped tagging when need_distractors=False (verified_match
with existing distractors), so retry_failed kept re-processing ~500+ tasks forever.

Usage:
    docker exec content-worker python /app/scripts/backfill_choices_complete.py --dry-run
    docker exec content-worker python /app/scripts/backfill_choices_complete.py
    docker exec content-worker python /app/scripts/backfill_choices_complete.py --class-level 8
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.distractor_gate import stored_distractors_valid

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

_SKIP_DIST_TYPES = frozenset({"text", "open_text", "coordinate"})


def fetch_candidates(engine, class_level: int | None) -> list[dict]:
    level_filter = ""
    params: dict = {}
    if class_level is not None:
        level_filter = "AND tb.class_level = :level"
        params["level"] = class_level

    sql = f"""
        SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
               tm.distractor_meta, tm.tags, tm.verification_status
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE (
          tm.tags->>'smart_verify_status' IN (
            'verified_match', 'verified_corrected', 'generated_from_scratch'
          )
          OR COALESCE(tm.tags->>'distractor_regen_pending', 'false') = 'true'
        )
        AND jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) >= 3
        AND COALESCE(tm.tags->>'choices_complete', 'false') != 'true'
        {level_filter}
        ORDER BY tm.id
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().fetchall()
    return [dict(r) for r in rows]


def should_finalize(row: dict) -> tuple[bool, str]:
    atype = (row.get("answer_type") or "").lower()
    if atype in _SKIP_DIST_TYPES:
        return True, "text_type_skip"

    dmeta = row.get("distractor_meta")
    if not isinstance(dmeta, list):
        try:
            dmeta = json.loads(dmeta or "[]")
        except Exception:
            dmeta = []

    if len(dmeta) < 3:
        return False, "count_lt_3"

    if stored_distractors_valid(
        dmeta,
        question=row.get("question_text") or "",
        correct_answer=row.get("correct_answer") or "",
        answer_type=atype,
    ):
        return True, "gate_valid"

    # Lenient: 3 stored items with value fields — gate may be strict on legacy data
    vals = [str(d.get("value", "")).strip() for d in dmeta[:3] if isinstance(d, dict)]
    if len(vals) >= 3 and all(len(v) >= 1 for v in vals):
        return True, "len3_has_values"

    return False, "invalid_distractors"


def apply_backfill(engine, rows: list[dict], dry_run: bool) -> dict[str, int]:
    stats = {"candidates": len(rows), "finalized": 0, "skipped": 0}

    for row in rows:
        ok, reason = should_finalize(row)
        if not ok:
            stats["skipped"] += 1
            log.debug("skip %s: %s", row["id"], reason)
            continue

        tags = row.get("tags") or {}
        if isinstance(tags, str):
            tags = json.loads(tags)
        tags = dict(tags)
        tags["choices_complete"] = True
        tags.pop("distractor_regen_pending", None)
        tags["distractor_backfill_reason"] = reason

        stats["finalized"] += 1
        if dry_run:
            log.info("[dry-run] finalize %s (%s)", row["id"], reason)
            continue

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET tags = CAST(:tags AS jsonb),
                        verification_status = 'verified'
                    WHERE id = :id
                """),
                {
                    "id": row["id"],
                    "tags": json.dumps(tags, ensure_ascii=False),
                },
            )

    return stats


def main() -> int:
    p = argparse.ArgumentParser(description="Backfill choices_complete for verified tasks")
    p.add_argument("--class-level", type=int, default=8)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    engine = create_engine(get_settings().database_url)
    rows = fetch_candidates(engine, args.class_level)
    log.info("G%d candidates with 3+ distractors, choices_complete=false: %d",
             args.class_level, len(rows))

    stats = apply_backfill(engine, rows, args.dry_run)
    log.info("Done: finalized=%d skipped=%d (of %d)",
             stats["finalized"], stats["skipped"], stats["candidates"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
