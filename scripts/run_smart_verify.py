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
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
from pathlib import Path
import signal
import sys
import time
import uuid

# Support both the production container (``/app``) and a direct local launch
# from the repository.  The command documented at the top of this file must
# not depend on the caller having already configured PYTHONPATH.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if "/app" not in sys.path:
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
    SUCCESS_STATUSES,
    bump_failed_retry_counter,
    distractors_valid,
    run_distractor_only_pipeline,
    sync_verify_tags,
)
from src.pipeline.smart_verify import run_smart_verify_pipeline
from src.pipeline.smart_verify_text import run_text_verify_pipeline
from src.schemas.smart_verify import SmartVerifyResponse
from src.pipeline.deepseek_client import (
    configure_global_request_limiter,
    global_request_limiter_stats,
)


# A claim lives only in ``tags`` while a worker owns a task.  It prevents two
# independently started processes from sending the same task to the model and
# then racing to persist incompatible snapshots.  Claims are deliberately
# short-lived operational metadata, never educational content.
DEFAULT_CLAIM_TTL_SECONDS = 30 * 60
COORDINATOR_ADVISORY_LOCK_KEY = 0x534D415254565246  # "SMARTVRF"


def configure_run_log(run_id: str, log_dir: str) -> Path:
    """Attach one durable file handler for this coordinator run."""
    destination = Path(log_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    log_path = destination / f"smart_verify_{run_id}.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(threadName)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logging.getLogger().addHandler(handler)
    return log_path


def acquire_coordinator_lock(engine):
    """Hold a PostgreSQL advisory lock for the lifetime of one coordinator."""
    conn = engine.connect()
    acquired = bool(conn.execute(
        text("SELECT pg_try_advisory_lock(:lock_key)"),
        {"lock_key": COORDINATOR_ADVISORY_LOCK_KEY},
    ).scalar_one())
    if not acquired:
        conn.close()
        return None
    return conn


def release_coordinator_lock(conn) -> None:
    if conn is None:
        return
    try:
        conn.execute(
            text("SELECT pg_advisory_unlock(:lock_key)"),
            {"lock_key": COORDINATOR_ADVISORY_LOCK_KEY},
        )
    finally:
        conn.close()


def _parse_levels(args: argparse.Namespace) -> tuple[int, ...]:
    if args.grades:
        parts = args.grades.split("-", 1)
        if len(parts) == 1:
            return (int(parts[0]),)
        a, b = parts
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
    queue_kind: str | None = None,
    source_run_id: str | None = None,
    response_run_id: str | None = None,
    replay_run_id: str | None = None,
) -> list:
    level_sql = ", ".join(str(x) for x in levels)
    params: dict = {"limit": limit}
    source_run_filter = ""
    if source_run_id:
        source_run_filter = "AND tm.tags->>'smart_verify_run_id' = :source_run_id"
        params["source_run_id"] = source_run_id

    if queue_kind is None:
        if gaps_only:
            queue_kind = "distractor"
        elif retry_failed:
            queue_kind = "retry"
        elif only_human_review:
            queue_kind = "human"
        elif reprocess:
            queue_kind = "legacy_reprocess"
        else:
            queue_kind = "answer"

    status_filter = ""
    if queue_kind == "distractor":
        gap_type_exclude = (
            ""
            if all_gap_types
            else "AND tm.answer_type NOT IN ('text', 'open_text', 'coordinate')"
        )
        # Do not infer completeness from JSON length or choices_complete.  The
        # coordinator evaluates every candidate with the complete Python
        # distractor gate before deciding whether an LLM call is necessary.
        status_filter = f"""
          AND tm.verification_status = 'pending'
          AND tm.tags->>'smart_verify_status' IN (
            'verified_match', 'verified_corrected', 'generated_from_scratch'
          )
          {gap_type_exclude}
        """
    elif queue_kind == "retry":
        # Failed answer verification only. Distractor repair is a different queue.
        status_filter = """
          AND tm.verification_status = 'pending'
          AND COALESCE(tm.tags->>'smart_verify_status', 'pending') IN (
            'failed_at_llm', 'failed_at_sympy'
          )
        """
    elif queue_kind == "replay":
        # Re-run the current local gate over a prior model result.  This queue
        # is intentionally restricted to failed SymPy rows with complete
        # evidence: no answer is trusted merely because an old LLM run exists.
        status_filter = """
          AND tm.verification_status = 'pending'
          AND tm.tags->>'smart_verify_status' = 'failed_at_sympy'
          AND NULLIF(tm.tags->>'answer_gemini_candidate', '') IS NOT NULL
          AND NULLIF(tm.tags->>'sympy_compatible_string', '') IS NOT NULL
          -- Response-style legacy rows are handled by the dedicated safe
          -- response queue.  A numeric replay must never re-route them and
          -- spend another text-model call on the same evidence.
          AND COALESCE(tm.tags->>'smart_verify_effective_answer_type', '') != 'text'
          -- Replaying the same immutable evidence twice in one run cannot
          -- change a proof result. Mark and exclude it after the first pass.
          AND COALESCE(tm.tags->>'smart_verify_replay_run_id', '') != :replay_run_id
          AND COALESCE(tm.tags->>'smart_verify_run_id', '') != :replay_run_id
        """
        params["replay_run_id"] = replay_run_id or ""
    elif queue_kind == "boolean":
        # Older code-execution responses sometimes contained only ``True``
        # after substituting a candidate into an equation.  That is evidence
        # of a check, not the answer itself. Re-run exactly this isolated
        # class with the strengthened prompt; source answers remain protected
        # by the textbook authority on every mismatch.
        status_filter = """
          AND tm.verification_status = 'pending'
          AND tm.tags->>'smart_verify_status' = 'failed_at_sympy'
          AND tm.tags->>'smart_verify_error' = 'invalid_boolean_result'
          AND COALESCE(tm.tags->>'smart_verify_effective_answer_type', '') != 'text'
        """
    elif queue_kind == "human":
        status_filter = """
          AND tm.verification_status = 'pending'
          AND tm.tags->>'smart_verify_status' = 'needs_human_review'
        """
    elif queue_kind == "arbitration":
        # A final, source-blind three-solver route for rows the ordinary
        # verifier could not certify.  It is isolated from retries: a source
        # correction can happen only after unanimous independent evidence,
        # never merely because a retry budget ran out.
        status_filter = """
          AND tm.verification_status = 'pending'
          AND COALESCE(tm.tags->>'smart_verify_status', '') IN (
            'failed_at_llm', 'failed_at_sympy', 'needs_human_review'
          )
          AND (
            COALESCE(tm.tags->>'smart_verify_retry_exhausted', 'false') = 'true'
            OR COALESCE(tm.tags->>'human_reprocess_exhausted', 'false') = 'true'
          )
          AND COALESCE(tm.tags->>'smart_verify_arbitration_finalized', 'false') != 'true'
        """
    elif queue_kind == "response":
        # Historical imports occasionally marked a response-style answer
        # (yes/no, a name, a verbal conclusion) as exact_number.  These rows
        # need the existing response-aware Smart Verify route, not another
        # SymPy retry.  Do not exclude exhausted rows: their former failure
        # was caused by the wrong route, not by a depleted retry budget.
        status_filter = """
          AND tm.verification_status = 'pending'
          AND tm.tags->>'smart_verify_status' IN (
            'failed_at_llm', 'failed_at_sympy', 'needs_human_review'
          )
          AND tm.answer_type IN ('exact_number', 'decimal', 'fraction')
          AND (
            COALESCE(tm.correct_answer, '') ~ '[А-Яа-яЁё]{3,}'
            OR COALESCE(tm.correct_answer, '') ~* '(^|[^а-яё])(да|нет|верно|неверно)([^а-яё]|$)'
          )
          -- This is a one-pass recovery queue.  A review outcome is a
          -- deliberate terminal result, not a reason to call the model again
          -- in this or any later response-recovery coordinator.  A later
          -- human-approved repair can explicitly clear this evidence marker.
          AND COALESCE(tm.tags->>'smart_verify_effective_answer_type', '') != 'text'
        """
    elif queue_kind == "answer":
        # Only never-processed answers. Failed answers and distractors have
        # their own queues and cannot overlap this snapshot.
        status_filter = """
          AND tm.verification_status = 'pending'
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

    queue_skip = """
      AND COALESCE(tm.tags->>'needs_compound_split', 'false') != 'true'
      AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'
      -- A task already audited as mathematically invalid is a content-review
      -- item, not a candidate for automatic answer verification.  Keeping it
      -- out of every operational queue prevents a model from manufacturing a
      -- plausible answer and accidentally certifying a broken source task.
      AND COALESCE(tm.tags->'content_quality'->>'status', '') != 'mathematically_invalid'
    """
    if queue_kind in ("answer", "retry"):
        queue_skip += """
          AND COALESCE(tm.tags->>'smart_verify_retry_exhausted', 'false') != 'true'
          -- A final human-review pass already recorded that this source
          -- cannot be safely certified automatically.  Do not spend later
          -- retry capacity on it unless a reviewer explicitly clears the
          -- terminal marker after repairing the source content.
          AND COALESCE(tm.tags->>'human_reprocess_exhausted', 'false') != 'true'
        """
    elif queue_kind == "arbitration":
        queue_skip += """
          AND COALESCE(tm.tags->>'smart_verify_arbitration_finalized', 'false') != 'true'
        """
    elif queue_kind == "distractor":
        queue_skip += """
          AND COALESCE(tm.tags->>'distractor_locked', 'false') != 'true'
          AND COALESCE(tm.tags->>'distractor_regen_exhausted', 'false') != 'true'
        """
    if task_id and reprocess:
        queue_skip = """
          AND COALESCE(tm.tags->>'needs_compound_split', 'false') != 'true'
          AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'
        """
    elif queue_kind == "human" and reprocess:
        queue_skip = """
          AND COALESCE(tm.tags->>'needs_compound_split', 'false') != 'true'
          AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'
          AND COALESCE(tm.tags->>'smart_verify_retry_exhausted', 'false') != 'true'
          AND COALESCE(tm.tags->>'human_reprocess_exhausted', 'false') != 'true'
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
    elif not levels:
        # A named global queue is intentionally independent of the textbook
        # hierarchy.  Historical imports may have neither ``toc_id`` nor a
        # mapped skill, and filtering them through a default grade silently
        # leaves real pending tasks unprocessed.
        level_clause = ""
    else:
        # Historical/generated tasks can legitimately have no toc_id. The
        # previous INNER JOIN route silently hid every such pending task from
        # Smart Verify. Prefer the textbook grade when available, then the
        # mapped skill grade, and finally the canonical G<grade>_ skill prefix.
        level_clause = f"""
          AND COALESCE(
            tb.class_level,
            kh.class_level_start,
            NULLIF(substring(tm.skill_id from '^G([0-9]+)_'), '')::integer
          ) IN ({level_sql})
        """
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
        LEFT JOIN textbook_toc toc ON toc.id = tm.toc_id
        LEFT JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        LEFT JOIN knowledge_hierarchy kh ON kh.id = tm.skill_id
        WHERE 1=1
          {level_clause}
          {type_filter}
          {status_filter}
          {reprocess_once_filter}
          {tag_filter}
          {queue_skip}
          {task_filter}
          {source_run_filter}
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


def claim_task(
    engine,
    task_id: str,
    claim_id: str,
    *,
    claim_ttl_seconds: int = DEFAULT_CLAIM_TTL_SECONDS,
) -> bool:
    """Atomically claim one task for this worker.

    Fetching is intentionally lightweight, so multiple coordinators can see
    the same candidate.  The conditional UPDATE below is the ownership
    boundary: exactly one worker may proceed.  A stale claim can be reclaimed
    after the TTL if a process was terminated mid-request.
    """
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE tasks_master AS tm
                SET tags = COALESCE(tm.tags, '{}'::jsonb)
                    || jsonb_build_object(
                        'smart_verify_claim_id', :claim_id,
                        'smart_verify_claimed_at', NOW()::text
                    ),
                    updated_at = NOW()
                WHERE tm.id = :task_id
                  AND (
                    NULLIF(tm.tags->>'smart_verify_claim_id', '') IS NULL
                    OR COALESCE(
                        CASE
                          WHEN COALESCE(tm.tags->>'smart_verify_claimed_at', '')
                               ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                          THEN (tm.tags->>'smart_verify_claimed_at')::timestamptz
                        END,
                        '-infinity'::timestamptz
                    ) < NOW() - make_interval(secs => :claim_ttl_seconds)
                  )
                RETURNING tm.id
            """),
            {
                "task_id": task_id,
                "claim_id": claim_id,
                "claim_ttl_seconds": int(claim_ttl_seconds),
            },
        )
        return result.scalar_one_or_none() is not None


def release_task_claim(engine, task_id: str, claim_id: str) -> bool:
    """Release only this worker's operational lease.

    Called from ``finally`` so Ctrl+C and unexpected exceptions do not leave a
    healthy task unavailable until the claim TTL expires.
    """
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE tasks_master
                SET tags = COALESCE(tags, '{}'::jsonb)
                    - 'smart_verify_claim_id'
                    - 'smart_verify_claimed_at',
                    updated_at = NOW()
                WHERE id = :task_id
                  AND tags->>'smart_verify_claim_id' = :claim_id
            """),
            {"task_id": task_id, "claim_id": claim_id},
        )
        return result.rowcount == 1


def release_all_run_claims(engine, claim_id: str) -> int:
    """Best-effort coordinator cleanup after normal exit or interruption."""
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE tasks_master
                SET tags = COALESCE(tags, '{}'::jsonb)
                    - 'smart_verify_claim_id'
                    - 'smart_verify_claimed_at'
                WHERE tags->>'smart_verify_claim_id' = :claim_id
            """),
            {"claim_id": claim_id},
        )
        return int(result.rowcount or 0)


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


def certify_final_verification(
    tags: dict,
    dmeta: list | None,
    *,
    question: str,
    correct_answer: str,
    answer_type: str,
) -> tuple[dict, str, bool]:
    """Derive the public status from answer success and the complete choice gate."""
    certified_tags = dict(tags)
    choices_valid = distractors_valid(
        dmeta,
        question=question,
        correct_answer=correct_answer,
        answer_type=answer_type,
    )
    if certified_tags.get("smart_verify_status") in SUCCESS_STATUSES and choices_valid:
        certified_tags["choices_complete"] = True
        certified_tags.pop("distractor_regen_pending", None)
        certified_tags.pop("distractor_regen_exhausted", None)
        return certified_tags, "verified", True
    certified_tags["choices_complete"] = False
    return certified_tags, "pending", False


def persist_result(
    engine,
    task_id: str,
    result: dict,
    *,
    source_question: str,
    source_answer: str | None,
    source_dmeta: list | None,
    answer_type: str,
    run_id: str,
    reprocess_run_id: str | None = None,
    claim_id: str | None = None,
) -> bool:
    tags = dict(result.get("tags") or {})
    # Never retain an operational lease in the final task metadata.
    tags.pop("smart_verify_claim_id", None)
    tags.pop("smart_verify_claimed_at", None)
    # Prose solutions are outside the Smart Verify data contract. Keeping old
    # values would let stale/generated reasoning leak into later consumers.
    tags.pop("step_by_step_solution", None)
    tags["smart_verify_run_id"] = run_id
    if reprocess_run_id:
        tags["smart_verify_reprocess_run_id"] = reprocess_run_id
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
    dmeta = result.get("distractor_meta")
    dmeta_json = json.dumps(dmeta if dmeta is not None else [], ensure_ascii=False)

    with engine.begin() as conn:
        current = conn.execute(
            text("""
                SELECT question_text, correct_answer, distractor_meta,
                       answer_type, tags
                FROM tasks_master
                WHERE id = :id
                FOR UPDATE
            """),
            {"id": task_id},
        ).fetchone()
        if current is None:
            log.warning("Skip persist for %s: task disappeared", task_id)
            return False
        current_tags = current[4] if isinstance(current[4], dict) else {}
        if claim_id is not None and current_tags.get("smart_verify_claim_id") != claim_id:
            log.warning("Skip persist for %s: Smart Verify claim was lost", task_id)
            return False
        # The coordinator may change the answer/distractors only from the exact
        # snapshot it verified. A concurrent editor wins and this stale result
        # is discarded without touching educational content.
        if (
            str(current[0] or "") != str(source_question or "")
            or str(current[1] or "") != str(source_answer or "")
            or (current[2] or []) != (source_dmeta or [])
            or str(current[3] or "") != str(answer_type or "")
        ):
            log.warning("Skip persist for %s: source snapshot changed concurrently", task_id)
            return False

        final_answer = str(result.get("correct_answer") or "")
        final_dmeta = dmeta if isinstance(dmeta, list) else []
        # Keep ``tasks_master.answer_type`` as immutable source metadata.  A
        # response-aware Smart Verify route records only an effective type in
        # audit tags, and certification then applies the matching choice gate.
        certification_answer_type = str(
            tags.get("smart_verify_effective_answer_type") or answer_type or "exact_number"
        )
        tags, vstatus, choices_valid = certify_final_verification(
            tags,
            final_dmeta,
            question=source_question or "",
            correct_answer=final_answer,
            answer_type=certification_answer_type,
        )

        old_answer = str(current[1] or "")
        if old_answer != final_answer:
            audit = list(tags.get("answer_change_audit") or [])
            audit.append({
                "run_id": run_id,
                "changed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "old_value": old_answer,
                "new_value": final_answer,
                "source": "smart_verify",
            })
            tags["answer_change_audit"] = audit
            tags["answer_previous"] = old_answer

        tags_json = json.dumps(tags, ensure_ascii=False)
        log.info("Persist tags_json: %s", tags_json)
        source_changed = old_answer != final_answer or (current[2] or []) != final_dmeta
        db_res = conn.execute(
            text("""
                UPDATE tasks_master
                SET correct_answer = :ans,
                    correct_answer_latex = COALESCE(NULLIF(:latex, ''), correct_answer_latex),
                    distractor_meta = cast(:dmeta as jsonb),
                    tags = cast(:tags as jsonb),
                    verification_status = :vstatus,
                    latex_status = CASE WHEN :source_changed THEN 'partial' ELSE latex_status END,
                    latex_normalized_at = CASE WHEN :source_changed THEN NOW() ELSE latex_normalized_at END,
                    updated_at = NOW()
                WHERE id = :id
                  AND (
                    :claim_id IS NULL
                    OR tags->>'smart_verify_claim_id' = :claim_id
                  )
            """),
            {
                "id": task_id,
                "ans": result["correct_answer"],
                "latex": result.get("correct_answer_latex") or "",
                "dmeta": dmeta_json,
                "tags": tags_json,
                "vstatus": vstatus,
                "claim_id": claim_id,
                "source_changed": source_changed,
            },
        )
        if db_res.rowcount != 1:
            log.warning(
                "Skip persist for %s: Smart Verify claim was lost or replaced",
                task_id,
            )
            return False
        log.info(
            "Persist result: updated %d rows for task %s; verification_status=%s; source_changed=%s",
            db_res.rowcount, task_id, vstatus, source_changed,
        )
    return True


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


def _mark_arbitration_finalized(
    engine,
    task_id: str,
    status: str,
    run_id: str,
) -> None:
    """Persist the outcome of one exhaustive arbitration without faking success."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tasks_master
                SET tags = COALESCE(tags, '{}'::jsonb)
                  || jsonb_build_object(
                    'smart_verify_arbitration_finalized', 'true',
                    'smart_verify_arbitration_status', :status,
                    'smart_verify_arbitration_run_id', :run_id
                  ),
                    updated_at = NOW()
                WHERE id = :id
            """),
            {"id": task_id, "status": status, "run_id": run_id},
        )


def run_batch(engine, args: argparse.Namespace) -> dict[str, int]:
    # Named queues are global unless an operator deliberately narrows them by
    # grade.  This includes historical imports with no hierarchy mapping.
    levels = _parse_levels(args) if (args.class_level or args.grades) else ()
    if args.task_id and not args.class_level and not args.grades:
        levels = (5, 6, 7, 8, 9, 10, 11)
    queue_kind = getattr(args, "queue", None)
    if queue_kind is None:
        if args.gaps_only:
            queue_kind = "distractor"
        elif args.retry_failed:
            queue_kind = "retry"
        elif args.only_human_review:
            queue_kind = "human"
        else:
            queue_kind = "answer"
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
        queue_kind=queue_kind,
        source_run_id=getattr(args, "source_run_id", None),
        response_run_id=None,
        replay_run_id=args.run_id if queue_kind == "replay" else None,
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
        "claimed_elsewhere": 0,
        "conflict": 0,
        "closed_without_llm": 0,
    }

    def process_one(row) -> dict[str, object]:
        tid, question, answer, atype, dmeta_raw, tags_raw = row
        tags = tags_raw if isinstance(tags_raw, dict) else json.loads(tags_raw or "{}")
        dmeta = dmeta_raw if isinstance(dmeta_raw, list) else json.loads(dmeta_raw or "[]")

        if args.dry_run:
            valid_now = queue_kind == "distractor" and distractors_valid(
                dmeta,
                question=question or "",
                correct_answer=answer or "",
                answer_type=atype or "exact_number",
            )
            log.info(
                "[dry-run] %s %s (%s)",
                "would close without LLM" if valid_now else "would process",
                tid,
                atype,
            )
            return {
                "processed": 1,
                "status": "dry_run",
                "action": "dist_ok" if valid_now else "dry_run",
                "closed_without_llm": int(valid_now),
            }

        if not claim_task(
            engine,
            tid,
            args.claim_id,
            claim_ttl_seconds=args.claim_ttl_seconds,
        ):
            log.info("Skip %s: claimed by another Smart Verify worker", tid)
            return {"claimed_elsewhere": 1}

        try:
            log.info("Smart verify: %s (%s), queue=%s", tid, atype, queue_kind)
            prev_status = tags.get("smart_verify_status", "pending")

            try:
                if queue_kind == "distractor":
                    result = run_distractor_only_pipeline(
                        task_id=tid,
                        question=question or "",
                        correct_answer=answer or "",
                        answer_type=atype or "exact_number",
                        distractor_meta=dmeta,
                        tags=tags,
                    )
                elif queue_kind == "replay":
                    prior = SmartVerifyResponse(
                        absolute_correct_answer=str(
                            tags.get("answer_gemini_candidate") or ""
                        ),
                        sympy_compatible_string=str(
                            tags.get("sympy_compatible_string") or ""
                        ),
                    )
                    result = run_smart_verify_pipeline(
                        task_id=tid,
                        question=question or "",
                        correct_answer=answer,
                        answer_type=atype or "exact_number",
                        distractor_meta=dmeta,
                        tags=tags,
                        answer_authority=args.answer_authority,
                        precomputed_response=prior,
                        # Replay should be bounded even for pathological
                        # historical SymPy strings.  It runs without a model
                        # call and defers any distractor generation below.
                        precomputed_gate_timeout_seconds=20,
                        allow_distractor_generation=False,
                    )
                    # Replay is a local re-evaluation of the same saved model
                    # evidence, not an additional model attempt. A parser
                    # upgrade must never exhaust a task's LLM retry budget.
                    result["tags"]["smart_verify_replay_run_id"] = args.run_id
                    new_status = result["tags"].get("smart_verify_status", "unknown")
                elif queue_kind == "response":
                    # The response queue is selected specifically for legacy
                    # rows whose source ``answer_type`` says numeric but whose
                    # stored answer is semantic prose, a comparison, or a
                    # multi-part conclusion.  Invoke the text route directly
                    # instead of relying on a second heuristic in the generic
                    # pipeline.  Source text remains immutable on mismatch.
                    result = run_text_verify_pipeline(
                        task_id=tid,
                        question=question or "",
                        correct_answer=answer,
                        answer_type="text",
                        distractor_meta=dmeta,
                        tags=tags,
                        answer_authority=args.answer_authority,
                        preserve_source_on_mismatch=True,
                        # The response queue exists for semantic legacy
                        # answers.  It has no SymPy proof path, so three
                        # independent answers are mandatory here as well.
                        require_unanimous_consensus=True,
                    )
                    result_tags = dict(result.get("tags") or {})
                    result_tags["smart_verify_effective_answer_type"] = "text"
                    result_tags["smart_verify_source_answer_type"] = atype or ""
                    result["tags"] = result_tags
                    new_status = result_tags.get("smart_verify_status", "unknown")
                else:
                    result = run_smart_verify_pipeline(
                        task_id=tid,
                        question=question or "",
                        correct_answer=answer,
                        answer_type=atype or "exact_number",
                        distractor_meta=dmeta,
                        tags=tags,
                        answer_authority=args.answer_authority,
                        require_unanimous_consensus=(queue_kind == "arbitration"),
                        allow_source_correction=(queue_kind == "arbitration"),
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

            persisted = persist_result(
                engine,
                tid,
                result,
                source_question=question or "",
                source_answer=answer,
                source_dmeta=dmeta,
                answer_type=atype or "exact_number",
                run_id=args.run_id,
                reprocess_run_id=getattr(args, "reprocess_run_id", None),
                claim_id=args.claim_id,
            )
            if not persisted:
                return {"conflict": 1}

            if queue_kind == "human":
                new_status = result["tags"].get("smart_verify_status", "")
                if new_status in (
                    "needs_human_review",
                    "failed_at_llm",
                    "failed_at_sympy",
                ):
                    _mark_human_reprocess_exhausted(engine, tid, new_status)
            elif queue_kind == "arbitration":
                new_status = result["tags"].get("smart_verify_status", "")
                if new_status not in SUCCESS_STATUSES:
                    _mark_arbitration_finalized(
                        engine, tid, new_status, args.run_id,
                    )

            status = result["tags"].get("smart_verify_status", "unknown")
            action = result.get("action", "")
            log.info("  → %s | %s", status, action)

            if args.sleep > 0:
                time.sleep(args.sleep)
            return {
                "processed": 1,
                "status": status,
                "action": action,
                "closed_without_llm": int(
                    queue_kind == "distractor" and "+dist_ok" in action
                ),
            }
        finally:
            try:
                release_task_claim(engine, tid, args.claim_id)
            except Exception:
                log.exception("Failed to release claim for %s", tid)

    workers = max(1, int(getattr(args, "workers", 1)))
    log.info(
        "Coordinator batch: queue=%s tasks=%d workers=%d run_id=%s",
        queue_kind, len(rows), workers, args.run_id,
    )
    def record(outcome: dict[str, object]) -> None:
        for key in ("processed", "claimed_elsewhere", "conflict", "closed_without_llm"):
            stats[key] += int(outcome.get(key, 0))
        status = str(outcome.get("status", ""))
        action = str(outcome.get("action", ""))
        if status in stats:
            stats[status] += 1
        elif action == "needs_compound_split":
            stats["needs_compound_split"] += 1
        if "+new_dist" in action:
            stats["new_dist"] += 1

    # For regular queues this is direct work in a worker.  For replay, the
    # SymPy gate itself uses an isolated child process in each worker, so the
    # per-task timeout remains hard while the coordinator can still use safe
    # bounded parallelism.
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="smart-verify") as pool:
        futures = [pool.submit(process_one, row) for row in rows]
        for future in as_completed(futures):
            record(future.result())

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
        help="Legacy alias for --queue retry",
    )
    p.add_argument(
        "--gaps-only",
        action="store_true",
        help="Legacy alias for --queue distractor",
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
    p.add_argument(
        "--queue",
        choices=(
            "answer", "distractor", "retry", "replay", "boolean", "human",
            "response", "arbitration",
        ),
        default=None,
        help="Non-overlapping operational queue",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Worker threads owned by this single coordinator",
    )
    p.add_argument(
        "--requests-per-minute",
        type=int,
        default=180,
        help="Shared limit for every HTTP attempt, including retries",
    )
    p.add_argument("--run-id", type=str, default=None)
    p.add_argument(
        "--source-run-id",
        type=str,
        default=None,
        help="Restrict this run to tasks touched by an exact earlier run ID",
    )
    p.add_argument(
        "--log-dir",
        type=str,
        default=str(Path(PROJECT_ROOT) / "logs" / "smart_verify"),
    )
    p.add_argument(
        "--claim-ttl-seconds",
        type=int,
        default=DEFAULT_CLAIM_TTL_SECONDS,
        help="How long a crashed worker's Smart Verify claim remains exclusive",
    )
    args = p.parse_args()

    # Named global queues carry their own selection predicates.  Requiring an
    # arbitrary grade here silently excludes valid rows and makes a global
    # recovery run impossible to launch.  Grade/task filters remain optional
    # narrowers for operators who explicitly provide them.
    if (
        not args.class_level
        and not args.grades
        and not args.task_id
        and not args.queue
    ):
        p.error("Specify --class-level, --grades, or --task-id")
    if args.only_fix_g7_reprocess_failed and not args.reprocess:
        p.error("--only-fix-g7-reprocess-failed requires --reprocess")
    if args.only_fix_g7_failed and not args.reprocess:
        p.error("--only-fix-g7-failed requires --reprocess")
    if args.only_fix_g6_reverify and not args.reprocess:
        p.error("--only-fix-g6-reverify requires --reprocess")
    if args.only_human_review and not args.reprocess:
        p.error("--only-human-review requires --reprocess")
    if args.queue and any((args.gaps_only, args.retry_failed, args.only_human_review)):
        p.error("--queue cannot be combined with legacy queue flags")
    if not 1 <= args.workers <= 64:
        p.error("--workers must be between 1 and 64")
    if not 1 <= args.requests_per_minute <= 250:
        p.error("--requests-per-minute must be between 1 and 250")

    engine = create_engine(
        get_settings().database_url,
        pool_size=max(10, args.workers + 4),
        max_overflow=max(10, args.workers),
        pool_pre_ping=True,
    )
    if args.claim_ttl_seconds < 60:
        p.error("--claim-ttl-seconds must be at least 60")
    args.run_id = args.run_id or (
        time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "_" + uuid.uuid4().hex[:8]
    )
    args.claim_id = args.run_id
    log_path = configure_run_log(args.run_id, args.log_dir)
    configure_global_request_limiter(args.requests_per_minute)
    log.info(
        "Smart Verify coordinator run_id=%s workers=%d rpm=%d log=%s",
        args.run_id, args.workers, args.requests_per_minute, log_path,
    )

    if args.reprocess:
        args.reprocess_run_id = args.run_id
        log.info("Reprocess run_id=%s (one pass per --loop)", args.reprocess_run_id)
    else:
        args.reprocess_run_id = None

    coordinator_conn = acquire_coordinator_lock(engine)
    if coordinator_conn is None:
        log.error("Another Smart Verify coordinator already owns the global lock")
        return 2
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def _raise_interrupt(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _raise_interrupt)
    try:
        if args.loop and not args.dry_run:
            total: dict[str, int] = {}
            while True:
                batch = run_batch(engine, args)
                if batch.get("processed", 0) == 0:
                    break
                for key, value in batch.items():
                    total[key] = total.get(key, 0) + value
                log.info("Batch checkpoint: %s", batch)
            log.info("FINAL STATS: %s", total)
        else:
            stats = run_batch(engine, args)
            log.info("STATS: %s", stats)
        log.info("MODEL LIMITER: %s", global_request_limiter_stats())
    except KeyboardInterrupt:
        log.warning("Coordinator interrupted; waiting for active workers to release leases")
        return 130
    finally:
        released = release_all_run_claims(engine, args.claim_id)
        if released:
            log.warning("Released %d leftover claims for run_id=%s", released, args.run_id)
        release_coordinator_lock(coordinator_conn)
        signal.signal(signal.SIGTERM, previous_sigterm)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
