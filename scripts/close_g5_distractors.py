#!/usr/bin/env python3
"""Close G5 text distractor gaps — LLM pipeline, loop until done."""
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
from src.pipeline.smart_verify_common import run_distractor_only_pipeline

log = logging.getLogger("close_g5_distractors")
logging.basicConfig(level=logging.INFO, format="%(message)s")

CLASS_LEVEL = 5

FETCH_SQL = """
    SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
           tm.distractor_meta, tm.tags
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
    WHERE tb.class_level = :level
      AND tm.tags ? 'distractor_regen_pending'
      AND tm.answer_type IN ('text', 'open_text')
      AND COALESCE(tm.correct_answer, '') NOT IN ('', '—', '-')
      AND jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) < 2
      AND COALESCE(tm.tags->>'distractor_regen_exhausted', 'false') != 'true'
      AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'
      AND COALESCE(tm.tags->>'distractor_locked', 'false') != 'true'
      AND tm.tags->>'smart_verify_status' IN (
        'verified_match', 'verified_corrected', 'generated_from_scratch'
      )
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


def run_pass(engine, *, limit: int, sleep: float) -> dict[str, int]:
    stats = {"processed": 0, "ok": 0, "partial": 0, "fail": 0}
    with engine.connect() as conn:
        rows = conn.execute(text(FETCH_SQL), {"level": CLASS_LEVEL, "limit": limit}).fetchall()

    if not rows:
        return stats

    for row in rows:
        tid, question, answer, atype, dmeta_raw, tags_raw = row
        tags = _tags(tags_raw)
        dmeta = _dmeta(dmeta_raw)
        tags.pop("distractor_regen_exhausted", None)
        tags.pop("distractor_gate_rejected", None)
        tags["distractor_regen_attempts"] = 0
        stats["processed"] += 1
        log.info("DIST %s (%s) had %d", tid, atype, len(dmeta))
        try:
            result = run_distractor_only_pipeline(
                task_id=tid,
                question=question or "",
                correct_answer=answer or "",
                answer_type=atype or "text",
                distractor_meta=dmeta,
                tags=tags,
            )
        except Exception:
            log.exception("CRASH %s", tid)
            stats["fail"] += 1
            continue

        got = len(result.get("distractor_meta") or [])
        action = result.get("action", "")
        out_tags = result.get("tags") or {}
        if got >= 2:
            stats["ok"] += 1
            out_tags.pop("distractor_regen_pending", None)
            out_tags["choices_complete"] = True
            out_tags["fix_g5_text_dist"] = "pipeline_ok"
            result["tags"] = out_tags
            log.info("  → OK +%d | %s", got, action)
        elif out_tags.get("distractor_regen_pending") or "regen_pending" in action:
            stats["partial"] += 1
            log.info("  → regen_pending | %s", action)
        else:
            stats["fail"] += 1
            log.info("  → fail | %s", action)

        persist_result(engine, tid, result)

        if sleep > 0:
            time.sleep(sleep)

    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill G5 text distractor gaps")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--loop", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    total = {"processed": 0, "ok": 0, "partial": 0, "fail": 0}

    while True:
        stats = run_pass(engine, limit=args.limit, sleep=args.sleep)
        for k in total:
            total[k] += stats[k]
        log.info("BATCH: %s", stats)
        if stats["processed"] == 0:
            break
        if not args.loop:
            break
        time.sleep(2)

    log.info("TOTAL: %s", total)

    with engine.connect() as conn:
        gaps = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.answer_type IN ('text', 'open_text')
                  AND jsonb_array_length(COALESCE(tm.distractor_meta,'[]')) < 2
                """
            ),
            {"level": CLASS_LEVEL},
        ).scalar()
        regen = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags ? 'distractor_regen_pending'
                """
            ),
            {"level": CLASS_LEVEL},
        ).scalar()
    log.info("Remaining text gaps: %s | regen_pending: %s", gaps, regen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
