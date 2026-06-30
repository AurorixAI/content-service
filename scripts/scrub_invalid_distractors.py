#!/usr/bin/env python3
"""Re-validate stored distractors and regen tasks that fail the gate."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from scripts.run_smart_verify import persist_result
from src.core.config import get_settings
from src.pipeline.distractor_gate import stored_distractors_valid
from src.pipeline.smart_verify_common import run_distractor_only_pipeline

log = logging.getLogger("scrub_invalid_distractors")
logging.basicConfig(level=logging.INFO, format="%(message)s")

FETCH_SQL = """
    SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
           tm.distractor_meta, tm.tags
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
    WHERE tb.class_level = :level
      AND COALESCE(tm.correct_answer, '') NOT IN ('', '—', '-')
      AND jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) >= 1
      AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'
      AND COALESCE(tm.tags->>'distractor_locked', 'false') != 'true'
      AND tm.tags->>'smart_verify_status' IN (
        'verified_match', 'verified_corrected', 'generated_from_scratch'
      )
    ORDER BY tm.id
"""


def _tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(raw or "{}")


def _dmeta(raw) -> list:
    if isinstance(raw, list):
        return list(raw)
    return json.loads(raw or "[]")


def find_invalid(engine, class_level: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text(FETCH_SQL), {"level": class_level}).mappings().all()
    invalid: list[dict] = []
    for row in rows:
        dmeta = _dmeta(row["distractor_meta"])
        if not dmeta:
            continue
        try:
            ok = stored_distractors_valid(
                dmeta,
                question=row["question_text"] or "",
                correct_answer=row["correct_answer"] or "",
                answer_type=row["answer_type"] or "",
                min_count=2,
            )
        except Exception:
            log.exception("audit crash %s", row["id"])
            invalid.append(dict(row))
            continue
        if not ok:
            invalid.append(dict(row))
    return invalid


def regen_batch(engine, rows: list[dict], *, sleep: float) -> dict[str, int]:
    stats = {"processed": 0, "ok": 0, "partial": 0, "fail": 0}
    for row in rows:
        tid = row["id"]
        tags = _tags(row["tags"])
        dmeta = _dmeta(row["distractor_meta"])
        tags.pop("distractor_regen_exhausted", None)
        tags.pop("distractor_gate_rejected", None)
        tags["distractor_regen_attempts"] = 0
        stats["processed"] += 1
        log.info("REGEN %s (%s) — had %d dist", tid, row["answer_type"], len(dmeta))
        try:
            result = run_distractor_only_pipeline(
                task_id=tid,
                question=row["question_text"] or "",
                correct_answer=row["correct_answer"] or "",
                answer_type=row["answer_type"] or "exact_number",
                distractor_meta=[],
                tags=tags,
            )
        except Exception:
            log.exception("CRASH %s", tid)
            stats["fail"] += 1
            continue

        persist_result(engine, tid, result)
        got = len(result.get("distractor_meta") or [])
        new_ok = stored_distractors_valid(
            result.get("distractor_meta") or [],
            question=row["question_text"] or "",
            correct_answer=result.get("correct_answer") or row["correct_answer"] or "",
            answer_type=row["answer_type"] or "",
            min_count=2,
        )
        if got >= 2 and new_ok:
            stats["ok"] += 1
            log.info("  → OK %d dist (gate clean)", got)
        elif got >= 1:
            stats["partial"] += 1
            log.info("  → partial %d dist", got)
        else:
            stats["fail"] += 1
            log.info("  → fail | %s", result.get("action", ""))

        if sleep > 0:
            time.sleep(sleep)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="0 = all invalid")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--loop", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)

    while True:
        invalid = find_invalid(engine, args.class_level)
        log.info("G%d invalid distractor sets: %d", args.class_level, len(invalid))
        if args.dry_run:
            for row in invalid[:30]:
                log.info("  %s (%s)", row["id"], row["answer_type"])
            if len(invalid) > 30:
                log.info("  ... +%d more", len(invalid) - 30)
            return 0

        batch = invalid[: args.limit] if args.limit > 0 else invalid
        if not batch:
            log.info("All stored distractors pass gate.")
            return 0

        stats = regen_batch(engine, batch, sleep=args.sleep)
        log.info("BATCH: %s", stats)
        if not args.loop or stats["processed"] == 0:
            break
        time.sleep(2)

    remaining = len(find_invalid(engine, args.class_level))
    log.info("Remaining invalid: %d", remaining)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
