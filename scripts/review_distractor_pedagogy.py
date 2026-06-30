#!/usr/bin/env python3
"""
LLM pedagogy pass for gate-OK distractors — skip OK, rewrite weak error_logic only.

Does NOT regen values; tasks with reject_value get tag distractor_pedagogy_regen.

Usage:
  python scripts/review_distractor_pedagogy.py --class-level 8 --limit 20 --dry-run
  python scripts/review_distractor_pedagogy.py --class-level 8 --limit 15 --loop --sleep 1
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.distractor_gate import stored_distractors_valid
from src.pipeline.distractor_pedagogy import (
    apply_pedagogy_review,
    audit_distractor_pedagogy,
    distractor_logic_text,
    looks_generic_error_logic,
)

log = logging.getLogger("review_distractor_pedagogy")
logging.basicConfig(level=logging.INFO, format="%(message)s")

FETCH_SQL = """
    SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
           tm.distractor_meta, tm.tags
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
    WHERE tb.class_level = :level
      AND jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) >= 2
      AND COALESCE(tm.tags->>'distractor_locked', 'false') != 'true'
      AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'
      AND tm.tags->>'smart_verify_status' IN (
        'verified_match', 'verified_corrected', 'generated_from_scratch'
      )
      AND COALESCE(tm.tags->>'distractor_pedagogy_ok', 'false') != 'true'
    ORDER BY tm.id
    LIMIT :limit
"""


def _tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(raw or "{}")


def _dmeta(raw) -> list:
    if isinstance(raw, list):
        return list(raw)
    return json.loads(raw or "[]")


def _needs_llm(dmeta: list) -> bool:
    """Skip LLM when all error_logic already look concrete."""
    for d in dmeta[:3]:
        if looks_generic_error_logic(distractor_logic_text(d)):
            return True
    return False


def _save(engine, task_id: str, dmeta: list, tags: dict) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""
            UPDATE tasks_master
            SET distractor_meta = cast(:dmeta AS jsonb),
                tags = cast(:tags AS jsonb)
            WHERE id = :id
        """),
            {
                "id": task_id,
                "dmeta": json.dumps(dmeta, ensure_ascii=False),
                "tags": json.dumps(tags, ensure_ascii=False),
            },
        )


def process_row(engine, row: dict, *, dry_run: bool, force_llm: bool) -> str:
    tid = row["id"]
    q = row["question_text"] or ""
    ans = row["correct_answer"] or ""
    at = row["answer_type"] or ""
    dmeta = _dmeta(row["distractor_meta"])
    tags = _tags(row["tags"])

    if not stored_distractors_valid(
        dmeta, question=q, correct_answer=ans, answer_type=at, min_count=2
    ):
        log.info("  skip %s — gate fail (use scrub first)", tid)
        return "skip_gate"

    if not force_llm and not _needs_llm(dmeta):
        tags["distractor_pedagogy_ok"] = "true"
        tags["distractor_pedagogy_at"] = datetime.now(timezone.utc).isoformat()
        tags.pop("distractor_pedagogy_regen", None)
        if not dry_run:
            _save(engine, tid, dmeta, tags)
        return "auto_ok"

    if dry_run:
        weak = [distractor_logic_text(d)[:50] for d in dmeta if looks_generic_error_logic(distractor_logic_text(d))]
        log.info("  audit %s weak=%s", tid, weak or "llm_check")
        return "dry_run"

    review = audit_distractor_pedagogy(
        question=q,
        correct_answer=ans,
        answer_type=at,
        distractors=dmeta[:3],
    )
    new_meta, outcome = apply_pedagogy_review(dmeta, review)
    now = datetime.now(timezone.utc).isoformat()
    tags["distractor_pedagogy_at"] = now

    if outcome == "pass":
        tags["distractor_pedagogy_ok"] = "true"
        tags.pop("distractor_pedagogy_regen", None)
        if not dry_run:
            _save(engine, tid, new_meta, tags)
        log.info("  ok %s", tid)
        return "ok"

    if outcome == "needs_regen":
        tags["distractor_pedagogy_regen"] = "true"
        tags.pop("distractor_pedagogy_ok", None)
        if not dry_run:
            _save(engine, tid, dmeta, tags)
        log.info("  regen %s", tid)
        return "needs_regen"

    log.warning("  invalid review %s", tid)
    return "invalid"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int, default=8)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-llm", action="store_true", help="LLM audit even if error_logic looks concrete")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    stats = {"auto_ok": 0, "ok": 0, "needs_regen": 0, "skip_gate": 0, "dry_run": 0, "invalid": 0}

    while True:
        with engine.connect() as conn:
            rows = conn.execute(
                text(FETCH_SQL), {"level": args.class_level, "limit": args.limit}
            ).mappings().all()

        if not rows:
            log.info("G%d pedagogy queue empty.", args.class_level)
            break

        log.info("G%d batch: %d tasks", args.class_level, len(rows))
        for row in rows:
            outcome = process_row(
                engine, dict(row), dry_run=args.dry_run, force_llm=args.force_llm
            )
            stats[outcome] = stats.get(outcome, 0) + 1
            if args.sleep > 0 and not args.dry_run:
                time.sleep(args.sleep)

        log.info("BATCH %s", stats)
        if not args.loop:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
