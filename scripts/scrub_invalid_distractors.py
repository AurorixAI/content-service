#!/usr/bin/env python3
"""Re-validate stored distractors and regen tasks that fail the gate."""
from __future__ import annotations

import argparse
import copy
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


def _is_gap(dmeta: list) -> bool:
    return len(dmeta) < 2


def _is_gate_fail(row: dict, dmeta: list) -> bool:
    if _is_gap(dmeta):
        return True
    try:
        return not stored_distractors_valid(
            dmeta,
            question=row["question_text"] or "",
            correct_answer=row["correct_answer"] or "",
            answer_type=row["answer_type"] or "",
            min_count=2,
        )
    except Exception:
        return True


def find_invalid(engine, class_level: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text(FETCH_SQL), {"level": class_level}).mappings().all()
    invalid: list[dict] = []
    for row in rows:
        dmeta = _dmeta(row["distractor_meta"])
        if _is_gate_fail(row, dmeta):
            invalid.append(dict(row))
    return invalid


def _regen_input_meta(dmeta: list, *, force_wipe: bool) -> list:
    """
    Gaps: same as run_smart_verify --gaps-only (keep existing meta, top-up).
    Gate-fail with dist>=2: optional full wipe when --force-wipe.
    """
    if force_wipe and len(dmeta) >= 2:
        return []
    return list(dmeta)


def regen_batch(
    engine,
    rows: list[dict],
    *,
    sleep: float,
    force_wipe: bool,
) -> dict[str, int]:
    stats = {"processed": 0, "ok": 0, "partial": 0, "fail": 0, "skipped_persist": 0}
    for row in rows:
        tid = row["id"]
        tags = _tags(row["tags"])
        backup_dmeta = copy.deepcopy(_dmeta(row["distractor_meta"]))
        tags.pop("distractor_regen_exhausted", None)
        tags.pop("distractor_gate_rejected", None)
        tags["distractor_regen_attempts"] = int(tags.get("distractor_regen_attempts") or 0) + 1
        stats["processed"] += 1
        mode = "gap" if _is_gap(backup_dmeta) else "gate_fail"
        log.info(
            "REGEN %s (%s) — had %d dist [%s]",
            tid,
            row["answer_type"],
            len(backup_dmeta),
            mode,
        )
        try:
            result = run_distractor_only_pipeline(
                task_id=tid,
                question=row["question_text"] or "",
                correct_answer=row["correct_answer"] or "",
                answer_type=row["answer_type"] or "exact_number",
                distractor_meta=_regen_input_meta(backup_dmeta, force_wipe=force_wipe),
                tags=tags,
            )
        except Exception:
            log.exception("CRASH %s", tid)
            stats["fail"] += 1
            continue

        got = len(result.get("distractor_meta") or [])
        new_ok = stored_distractors_valid(
            result.get("distractor_meta") or [],
            question=row["question_text"] or "",
            correct_answer=result.get("correct_answer") or row["correct_answer"] or "",
            answer_type=row["answer_type"] or "",
            min_count=2,
        )

        # Never persist a worse/empty set over a non-empty backup.
        if got < len(backup_dmeta) and not new_ok:
            stats["skipped_persist"] += 1
            stats["fail"] += 1
            log.info("  → fail (kept %d dist, not persisting wipe)", len(backup_dmeta))
            if sleep > 0:
                time.sleep(sleep)
            continue

        persist_result(engine, tid, result)

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
    ap.add_argument(
        "--force-wipe",
        action="store_true",
        help="Full regen (distractor_meta=[]) only for gate-fail with dist>=2",
    )
    ap.add_argument(
        "--gaps-only",
        action="store_true",
        help="Only tasks with <2 distractors (same path as smart_verify --gaps-only)",
    )
    ap.add_argument(
        "--gate-fail-only",
        action="store_true",
        help="Only tasks with dist>=2 that fail stored gate (not gaps)",
    )
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)

    while True:
        invalid = find_invalid(engine, args.class_level)
        if args.gaps_only:
            invalid = [r for r in invalid if _is_gap(_dmeta(r["distractor_meta"]))]
        if args.gate_fail_only:
            invalid = [r for r in invalid if not _is_gap(_dmeta(r["distractor_meta"]))]
        log.info("G%d invalid distractor sets: %d", args.class_level, len(invalid))
        if args.dry_run:
            for row in invalid[:30]:
                dmeta = _dmeta(row["distractor_meta"])
                log.info("  %s (%s) dist=%d", row["id"], row["answer_type"], len(dmeta))
            if len(invalid) > 30:
                log.info("  ... +%d more", len(invalid) - 30)
            return 0

        batch = invalid[: args.limit] if args.limit > 0 else invalid
        if not batch:
            log.info("All stored distractors pass gate.")
            return 0

        stats = regen_batch(engine, batch, sleep=args.sleep, force_wipe=args.force_wipe)
        log.info("BATCH: %s", stats)
        if not args.loop or stats["processed"] == 0:
            break
        time.sleep(2)

    remaining = len(find_invalid(engine, args.class_level))
    log.info("Remaining invalid: %d", remaining)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
