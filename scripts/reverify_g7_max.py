#!/usr/bin/env python3
"""
G7 max-quality reverify — reset human_review queue + prep split children.

Usage:
  python scripts/reverify_g7_max.py --prep-only
  python scripts/reverify_g7_max.py  # prep + print run commands
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.smart_verify_common import clear_stale_verify_flags

log = logging.getLogger("reverify_g7_max")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def _tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(raw or "{}")


def prep_human_review(engine, *, mark_coordinate_exhausted: bool = True) -> dict[str, int]:
    """Clear retry flags; optionally park coordinate tasks out of reprocess queue."""
    stats = {"human_reset": 0, "pending_reset": 0, "coordinate_parked": 0}
    with engine.begin() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.answer_type, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 7
                  AND (
                    tm.tags->>'smart_verify_status' = 'needs_human_review'
                    OR (
                      COALESCE(NULLIF(tm.tags->>'smart_verify_status', ''), 'pending') = 'pending'
                      AND tm.tags->>'split_from' IS NOT NULL
                    )
                  )
            """),
        ).all()
        for tid, atype, raw in rows:
            tags = _tags(raw)
            st = tags.get("smart_verify_status", "pending")
            for key in (
                "smart_verify_retry_exhausted",
                "smart_verify_retry_count",
                "distractor_regen_exhausted",
                "distractor_regen_attempts",
                "human_reprocess_exhausted",
                "human_reprocess_status",
            ):
                tags.pop(key, None)
            if st == "needs_human_review":
                err = tags.get("smart_verify_error") or ""
                if err.startswith("Compound") or err.startswith("G8 batch"):
                    tags.pop("smart_verify_error", None)
                    tags.pop("compound_warning", None)
                    tags.pop("needs_compound_split", None)
                if mark_coordinate_exhausted and (atype or "") == "coordinate":
                    tags["human_reprocess_exhausted"] = "true"
                    tags["human_reprocess_status"] = "coordinate_manual"
                    stats["coordinate_parked"] += 1
                clear_stale_verify_flags(tags)
                stats["human_reset"] += 1
            else:
                clear_stale_verify_flags(tags)
                stats["pending_reset"] += 1
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET tags = cast(:tags AS jsonb), updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": tid, "tags": json.dumps(tags, ensure_ascii=False)},
            )
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prep-only", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    stats = prep_human_review(engine)
    log.info("Prep done: %s", stats)

    if not args.prep_only:
        log.info(
            "Run:\n"
            "  1) python /app/scripts/run_smart_verify.py --class-level 7 --loop --limit 20\n"
            "  2) python /app/scripts/run_smart_verify.py --class-level 7 "
            "--only-human-review --reprocess --loop --limit 15 --sleep 1"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
