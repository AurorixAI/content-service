#!/usr/bin/env python3
"""
Smart Verify batch processor — code_execution compute + SymPy gate + distractors.

Usage:
  python scripts/run_smart_verify.py --class-level 8 --dry-run
  python scripts/run_smart_verify.py --class-level 8 --limit 50
  python scripts/run_smart_verify.py --task-id G8_TB_3_59.3
  python scripts/run_smart_verify.py --grades 5-8 --loop
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_smart_verify")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.smart_verify import run_smart_verify_pipeline


def _parse_levels(args: argparse.Namespace) -> tuple[int, ...]:
    if args.grades:
        a, b = args.grades.split("-", 1)
        return tuple(range(int(a), int(b) + 1))
    if args.class_level is not None:
        return (args.class_level,)
    raise SystemExit("Specify --class-level or --grades")


def fetch_tasks(
    engine,
    *,
    levels: tuple[int, ...],
    limit: int,
    task_id: str | None,
    reprocess: bool,
) -> list:
    level_sql = ", ".join(str(x) for x in levels)
    params: dict = {"limit": limit}

    status_filter = ""
    if not reprocess:
        status_filter = """
          AND COALESCE(tm.tags->>'smart_verify_status', 'pending') IN (
            'pending', 'failed_at_llm', 'failed_at_sympy'
          )
        """

    task_filter = ""
    if task_id:
        task_filter = "AND tm.id = :task_id"
        params["task_id"] = task_id

    sql = f"""
        SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
               tm.distractor_meta, tm.tags
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level IN ({level_sql})
          AND tm.answer_type IN (
            'exact_number', 'decimal', 'fraction', 'expression',
            'equation_solution', 'inequality', 'set', 'multiple_choice'
          )
          {status_filter}
          {task_filter}
        ORDER BY tb.class_level, tm.answer_type, tm.id
        LIMIT :limit
    """
    with engine.connect() as conn:
        return conn.execute(text(sql), params).fetchall()


def persist_result(engine, task_id: str, result: dict) -> None:
    tags_json = json.dumps(result["tags"], ensure_ascii=False)
    dmeta = result.get("distractor_meta")
    dmeta_json = json.dumps(dmeta if dmeta is not None else [], ensure_ascii=False)
    vstatus = result.get("verification_status", "pending")

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tasks_master
                SET correct_answer = :ans,
                    distractor_meta = cast(:dmeta as jsonb),
                    tags = cast(:tags as jsonb),
                    verification_status = :vstatus,
                    updated_at = NOW()
                WHERE id = :id
            """),
            {
                "id": task_id,
                "ans": result["correct_answer"],
                "dmeta": dmeta_json,
                "tags": tags_json,
                "vstatus": vstatus,
            },
        )


def run_batch(engine, args: argparse.Namespace) -> dict[str, int]:
    levels = _parse_levels(args)
    rows = fetch_tasks(
        engine,
        levels=levels,
        limit=args.limit,
        task_id=args.task_id,
        reprocess=args.reprocess,
    )

    if not rows:
        log.info("Queue empty for levels %s", levels)
        return {"processed": 0}

    stats = {
        "processed": 0,
        "verified_match": 0,
        "verified_corrected": 0,
        "generated_from_scratch": 0,
        "failed_at_llm": 0,
        "failed_at_sympy": 0,
        "needs_human_review": 0,
        "skipped": 0,
        "new_dist": 0,
    }

    for row in rows:
        tid, question, answer, atype, dmeta_raw, tags_raw = row
        tags = tags_raw if isinstance(tags_raw, dict) else json.loads(tags_raw or "{}")
        dmeta = dmeta_raw if isinstance(dmeta_raw, list) else json.loads(dmeta_raw or "[]")

        if args.dry_run:
            log.info("[dry-run] would process %s (%s)", tid, atype)
            stats["processed"] += 1
            continue

        log.info("Smart verify: %s (%s)", tid, atype)
        result = run_smart_verify_pipeline(
            task_id=tid,
            question=question or "",
            correct_answer=answer,
            answer_type=atype or "exact_number",
            distractor_meta=dmeta,
            tags=tags,
            answer_authority=args.answer_authority,
        )

        persist_result(engine, tid, result)
        stats["processed"] += 1

        status = result["tags"].get("smart_verify_status", "unknown")
        if status in stats:
            stats[status] += 1
        if "+new_dist" in result.get("action", ""):
            stats["new_dist"] += 1

        log.info("  → %s | %s", status, result.get("action", ""))

        if args.sleep > 0:
            time.sleep(args.sleep)

    return stats


def main() -> int:
    p = argparse.ArgumentParser(description="Smart Verify batch pipeline")
    p.add_argument("--class-level", type=int)
    p.add_argument("--grades", type=str, help="e.g. 5-8")
    p.add_argument("--task-id", type=str, help="Process single task")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--reprocess", action="store_true", help="Ignore smart_verify_status")
    p.add_argument("--loop", action="store_true", help="Run until queue empty")
    p.add_argument("--sleep", type=float, default=0.0, help="Pause between tasks (seconds)")
    p.add_argument(
        "--answer-authority",
        choices=["ai_first", "textbook", "ai_if_sympy_confirms"],
        default=None,
    )
    args = p.parse_args()

    if not args.class_level and not args.grades and not args.task_id:
        p.error("Specify --class-level, --grades, or --task-id")

    engine = create_engine(get_settings().database_url)

    if args.loop and not args.dry_run:
        total = {k: 0 for k in (
            "processed", "verified_match", "verified_corrected", "generated_from_scratch",
            "failed_at_llm", "failed_at_sympy", "needs_human_review", "skipped", "new_dist",
        )}
        while True:
            batch = run_batch(engine, args)
            if batch.get("processed", 0) == 0:
                break
            for k, v in batch.items():
                total[k] = total.get(k, 0) + v
            log.info("Batch done, sleeping 2s...")
            time.sleep(2)
        log.info("FINAL STATS: %s", total)
    else:
        stats = run_batch(engine, args)
        log.info("STATS: %s", stats)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
