#!/usr/bin/env python3
"""
Smart Verify batch processor — code_execution compute + SymPy gate + distractors.

Usage:
  python scripts/run_smart_verify.py --class-level 8 --dry-run
  python scripts/run_smart_verify.py --class-level 8 --limit 50
  python scripts/run_smart_verify.py --task-id G8_TB_3_59.3
  python scripts/run_smart_verify.py --grades 5-8 --loop
  python scripts/run_smart_verify.py --grades 5-8 --answer-type equation_solution --loop
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
from src.pipeline.smart_verify_common import (
    QUEUE_SKIP_SQL,
    SUCCESS_STATUSES,
    bump_failed_retry_counter,
    run_distractor_only_pipeline,
    sync_verify_tags,
)
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
    reprocess_run_id: str | None = None,
    retry_failed: bool = False,
    gaps_only: bool = False,
    skip_text: bool = False,
    answer_type: str | None = None,
    id_prefix: str | None = None,
    only_fix_g7_failed: bool = False,
    only_fix_g7_reprocess_failed: bool = False,
    only_fix_g6_reverify: bool = False,
    only_human_review: bool = False,
    skip_coordinate: bool = False,
    all_gap_types: bool = False,
) -> list:
    level_sql = ", ".join(str(x) for x in levels)
    params: dict = {"limit": limit}

    status_filter = ""
    if gaps_only:
        gap_type_exclude = (
            ""
            if all_gap_types
            else "AND tm.answer_type NOT IN ('text', 'open_text', 'coordinate')"
        )
        # Pending first-run + verified tasks missing distractors (no failed churn).
        status_filter = f"""
          AND (
            COALESCE(NULLIF(tm.tags->>'smart_verify_status', ''), 'pending') = 'pending'
            OR (
              tm.tags->>'smart_verify_status' IN (
                'verified_match', 'verified_corrected', 'generated_from_scratch'
              )
              AND jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) < 2
              {gap_type_exclude}
            )
            OR (
              COALESCE(tm.tags->>'distractor_regen_pending', 'false') = 'true'
              AND jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) < 2
              {gap_type_exclude}
            )
          )
        """
    elif retry_failed:
        # Failed tasks only — distractor gaps handled by --gaps-only (no overlap).
        status_filter = """
          AND COALESCE(tm.tags->>'smart_verify_status', 'pending') IN (
            'failed_at_llm', 'failed_at_sympy'
          )
        """
    elif only_human_review:
        status_filter = """
          AND tm.tags->>'smart_verify_status' = 'needs_human_review'
        """
    elif not reprocess:
        # Only never-processed tasks; failed_at_* retried separately after gate fixes.
        status_filter = """
          AND COALESCE(NULLIF(tm.tags->>'smart_verify_status', ''), 'pending') = 'pending'
        """

    # --reprocess: one pass per run_id — loop stops when every task has this tag.
    reprocess_once_filter = ""
    if reprocess_run_id:
        reprocess_once_filter = """
          AND COALESCE(tm.tags->>'smart_verify_run_id', '') != :reprocess_run_id
        """
        params["reprocess_run_id"] = reprocess_run_id

    tag_filter = ""
    if only_fix_g7_failed:
        tag_filter = "AND tm.tags->>'fix_g7_failed' = 'true'"
    elif only_fix_g7_reprocess_failed:
        tag_filter = "AND tm.tags->>'fix_g7_reprocess_failed' = 'true'"
    elif only_fix_g6_reverify:
        tag_filter = "AND tm.tags->>'fix_g6_reverify' = 'pending'"
    elif only_human_review:
        tag_filter = """
          AND COALESCE(tm.tags->>'human_reprocess_exhausted', 'false') != 'true'
        """

    queue_skip = QUEUE_SKIP_SQL
    if task_id and reprocess:
        queue_skip = """
          AND COALESCE(tm.tags->>'needs_compound_split', 'false') != 'true'
          AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'
        """
    elif only_human_review and reprocess:
        queue_skip = """
          AND COALESCE(tm.tags->>'needs_compound_split', 'false') != 'true'
          AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'
          AND COALESCE(tm.tags->>'smart_verify_retry_exhausted', 'false') != 'true'
        """
    elif (only_fix_g7_failed or only_fix_g7_reprocess_failed or only_fix_g6_reverify) and reprocess:
        # Allow re-running tasks marked choices_complete by bypass scripts.
        queue_skip = """
          AND COALESCE(tm.tags->>'distractor_regen_exhausted', 'false') != 'true'
          AND COALESCE(tm.tags->>'needs_compound_split', 'false') != 'true'
          AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'
        """
    task_filter = ""
    if task_id:
        task_filter = "AND tm.id = :task_id"
        params["task_id"] = task_id
        level_clause = ""
    else:
        level_clause = f"AND tb.class_level IN ({level_sql})"
        if id_prefix:
            task_filter = "AND tm.id LIKE :id_prefix"
            params["id_prefix"] = id_prefix + "%"

    if answer_type:
        type_filter = "AND tm.answer_type = :answer_type"
        params["answer_type"] = answer_type
    elif skip_coordinate:
        type_filter = "AND tm.answer_type != 'coordinate'"
    elif skip_text:
        type_filter = """
          AND tm.answer_type IN (
            'exact_number', 'decimal', 'fraction', 'expression',
            'equation_solution', 'inequality', 'set', 'multiple_choice'
          )
        """
    else:
        type_filter = """
          AND tm.answer_type IN (
            'exact_number', 'decimal', 'fraction', 'expression',
            'equation_solution', 'inequality', 'set', 'multiple_choice',
            'text', 'open_text', 'coordinate'
          )
        """

    sql = f"""
        SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
               tm.distractor_meta, tm.tags
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE 1=1
          {level_clause}
          {type_filter}
          {status_filter}
          {reprocess_once_filter}
          {tag_filter}
          {queue_skip}
          {task_filter}
        ORDER BY
          CASE
            WHEN COALESCE(NULLIF(tm.tags->>'smart_verify_status', ''), 'pending') = 'pending' THEN 0
            ELSE 1
          END,
          tb.class_level, tm.answer_type, tm.id
        LIMIT :limit
    """
    with engine.connect() as conn:
        return conn.execute(text(sql), params).fetchall()


def _pipeline_failure_result(
    *,
    answer: str | None,
    dmeta: list,
    tags: dict,
    prev_status: str,
    exc: BaseException,
) -> dict:
    """Isolate per-task crashes — mark failed, keep loop alive."""
    err_tags = dict(tags)
    sync_verify_tags(err_tags, "failed_at_sympy")
    err_tags["smart_verify_error"] = (
        f"pipeline_exception:{type(exc).__name__}:{str(exc)[:250]}"
    )
    bump_failed_retry_counter(err_tags, prev_status, "failed_at_sympy")
    return {
        "correct_answer": answer or "",
        "correct_answer_latex": "",
        "distractor_meta": dmeta,
        "tags": err_tags,
        "verification_status": "pending",
        "action": "failed_at_sympy",
    }


def persist_result(
    engine, task_id: str, result: dict, *, reprocess_run_id: str | None = None
) -> None:
    tags = dict(result.get("tags") or {})
    if reprocess_run_id:
        tags["smart_verify_run_id"] = reprocess_run_id
    if tags.get("smart_verify_status") in SUCCESS_STATUSES:
        tags.pop("fix_g7_failed", None)
        tags.pop("fix_g7_reprocess_failed", None)
        tags.pop("human_reprocess_exhausted", None)
        tags.pop("human_reprocess_status", None)
        tags["fix_g7_reprocessed"] = "true"
    if tags.get("smart_verify_status") in SUCCESS_STATUSES and tags.get("fix_g6_reverify"):
        tags.pop("fix_g6_failed", None)
        tags.pop("fix_g6_human_review", None)
        tags.pop("fix_g6_reverify", None)
        tags.pop("fix_g6_reverify_failed", None)
        tags.pop("fix_g6_reverify_human", None)
        tags["fix_g6_reverified"] = "true"
    elif tags.get("fix_g7_failed") == "true" and str(
        tags.get("smart_verify_status", "")
    ).startswith("failed"):
        tags.pop("fix_g7_failed", None)
        tags["fix_g7_reprocess_failed"] = "true"
    elif tags.get("fix_g7_reprocess_failed") == "true" and str(
        tags.get("smart_verify_status", "")
    ).startswith("failed"):
        tags.pop("fix_g7_reprocess_failed", None)
        tags["fix_g7_reprocess_failed2"] = "true"
    elif tags.get("fix_g7_reprocess_failed") == "true" and tags.get(
        "smart_verify_status"
    ) == "needs_human_review":
        tags.pop("fix_g7_reprocess_failed", None)
        tags["fix_g7_reprocess_human"] = "true"
    elif tags.get("fix_g6_reverify") == "pending" and str(
        tags.get("smart_verify_status", "")
    ).startswith("failed"):
        tags["fix_g6_reverify"] = "failed"
        tags["fix_g6_reverify_failed"] = tags.get("smart_verify_status", "failed")
    elif tags.get("fix_g6_reverify") == "pending" and tags.get(
        "smart_verify_status"
    ) == "needs_human_review":
        tags["fix_g6_reverify"] = "human"
        tags["fix_g6_reverify_human"] = "true"
    result = {**result, "tags": tags}
    tags_json = json.dumps(tags, ensure_ascii=False)
    log.info("Persist tags_json: %s", tags_json)
    dmeta = result.get("distractor_meta")
    dmeta_json = json.dumps(dmeta if dmeta is not None else [], ensure_ascii=False)
    vstatus = result.get("verification_status", "pending")

    with engine.begin() as conn:
        db_res = conn.execute(
            text("""
                UPDATE tasks_master
                SET correct_answer = :ans,
                    correct_answer_latex = COALESCE(NULLIF(:latex, ''), correct_answer_latex),
                    distractor_meta = cast(:dmeta as jsonb),
                    tags = cast(:tags as jsonb),
                    verification_status = :vstatus,
                    updated_at = NOW()
                WHERE id = :id
            """),
            {
                "id": task_id,
                "ans": result["correct_answer"],
                "latex": result.get("correct_answer_latex") or "",
                "dmeta": dmeta_json,
                "tags": tags_json,
                "vstatus": vstatus,
            },
        )
        log.info("Persist result: updated %d rows for task %s", db_res.rowcount, task_id)


def _mark_human_reprocess_exhausted(engine, task_id: str, status: str) -> None:
    """One human_review reprocess attempt — drop from queue if still not verified."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tasks_master
                SET tags = tags
                  || jsonb_build_object(
                    'human_reprocess_exhausted', 'true',
                    'human_reprocess_status', :status
                  ),
                    updated_at = NOW()
                WHERE id = :id
            """),
            {"id": task_id, "status": status},
        )


def run_batch(engine, args: argparse.Namespace) -> dict[str, int]:
    levels = _parse_levels(args) if (args.class_level or args.grades) else (8,)
    if args.task_id and not args.class_level and not args.grades:
        levels = (5, 6, 7, 8)
    rows = fetch_tasks(
        engine,
        levels=levels,
        limit=args.limit,
        task_id=args.task_id,
        reprocess=args.reprocess,
        reprocess_run_id=getattr(args, "reprocess_run_id", None),
        retry_failed=args.retry_failed,
        gaps_only=args.gaps_only,
        skip_text=args.skip_text,
        answer_type=args.answer_type,
        id_prefix=args.id_prefix,
        only_fix_g7_failed=args.only_fix_g7_failed,
        only_fix_g7_reprocess_failed=args.only_fix_g7_reprocess_failed,
        only_fix_g6_reverify=args.only_fix_g6_reverify,
        only_human_review=args.only_human_review,
        skip_coordinate=args.skip_coordinate,
        all_gap_types=args.all_gap_types,
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
        "needs_compound_split": 0,
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
        prev_status = tags.get("smart_verify_status", "pending")

        try:
            if args.gaps_only and prev_status in SUCCESS_STATUSES:
                result = run_distractor_only_pipeline(
                    task_id=tid,
                    question=question or "",
                    correct_answer=answer or "",
                    answer_type=atype or "exact_number",
                    distractor_meta=dmeta,
                    tags=tags,
                )
            else:
                result = run_smart_verify_pipeline(
                    task_id=tid,
                    question=question or "",
                    correct_answer=answer,
                    answer_type=atype or "exact_number",
                    distractor_meta=dmeta,
                    tags=tags,
                    answer_authority=args.answer_authority,
                )
                new_status = result["tags"].get("smart_verify_status", "unknown")
                bump_failed_retry_counter(result["tags"], prev_status, new_status)
        except Exception as exc:
            log.exception("Smart verify pipeline crashed on %s", tid)
            result = _pipeline_failure_result(
                answer=answer,
                dmeta=dmeta,
                tags=tags,
                prev_status=prev_status,
                exc=exc,
            )

        persist_result(
            engine, tid, result, reprocess_run_id=getattr(args, "reprocess_run_id", None)
        )

        if args.only_human_review:
            new_status = result["tags"].get("smart_verify_status", "")
            if new_status in (
                "needs_human_review",
                "failed_at_llm",
                "failed_at_sympy",
            ):
                _mark_human_reprocess_exhausted(engine, tid, new_status)

        stats["processed"] += 1

        status = result["tags"].get("smart_verify_status", "unknown")
        if status in stats:
            stats[status] += 1
        elif result.get("action") == "needs_compound_split":
            stats["needs_compound_split"] += 1
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
    p.add_argument(
        "--id-prefix",
        type=str,
        default=None,
        help="Only tasks whose id starts with prefix, e.g. G8_TB_",
    )
    p.add_argument(
        "--only-fix-g7-failed",
        action="store_true",
        help="Only tasks tagged fix_g7_failed=true (use with --reprocess)",
    )
    p.add_argument(
        "--only-human-review",
        action="store_true",
        help="Only needs_human_review tasks (use with --reprocess)",
    )
    p.add_argument(
        "--skip-coordinate",
        action="store_true",
        help="Exclude coordinate answer_type from batch",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--reprocess", action="store_true",
                   help="Re-run all tasks once (uses smart_verify_run_id; --loop stops after one pass)")
    p.add_argument(
        "--only-fix-g7-reprocess-failed",
        action="store_true",
        help="Only tasks tagged fix_g7_reprocess_failed=true (use with --reprocess)",
    )
    p.add_argument(
        "--only-fix-g6-reverify",
        action="store_true",
        help="Only G6 bypass tasks tagged fix_g6_reverify=pending (use with --reprocess)",
    )
    p.add_argument(
        "--retry-failed",
        action="store_true",
        help="failed_at_llm/sympy + tasks missing distractors",
    )
    p.add_argument(
        "--gaps-only",
        action="store_true",
        help="Only pending + verified tasks with <2 distractors (skip failed)",
    )
    p.add_argument(
        "--all-gap-types",
        action="store_true",
        help="With --gaps-only: include text/open_text/coordinate (default skips them)",
    )
    p.add_argument("--skip-text", action="store_true", help="Numeric/algebraic types only")
    p.add_argument(
        "--answer-type",
        type=str,
        default=None,
        help="Single answer_type filter, e.g. equation_solution",
    )
    p.add_argument("--loop", action="store_true", help="Run until queue empty")
    p.add_argument("--sleep", type=float, default=0.0, help="Pause between tasks (seconds)")
    p.add_argument(
        "--answer-authority",
        choices=["ai_first", "textbook", "ai_if_sympy_confirms"],
        default=None,
    )
    p.add_argument("--limit", type=int, default=50)
    args = p.parse_args()

    if not args.class_level and not args.grades and not args.task_id:
        p.error("Specify --class-level, --grades, or --task-id")
    if args.only_fix_g7_reprocess_failed and not args.reprocess:
        p.error("--only-fix-g7-reprocess-failed requires --reprocess")
    if args.only_fix_g7_failed and not args.reprocess:
        p.error("--only-fix-g7-failed requires --reprocess")
    if args.only_fix_g6_reverify and not args.reprocess:
        p.error("--only-fix-g6-reverify requires --reprocess")
    if args.only_human_review and not args.reprocess:
        p.error("--only-human-review requires --reprocess")

    engine = create_engine(get_settings().database_url)

    if args.reprocess:
        args.reprocess_run_id = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        log.info("Reprocess run_id=%s (one pass per --loop)", args.reprocess_run_id)
    else:
        args.reprocess_run_id = None

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
