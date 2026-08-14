"""Shared helpers for Smart Verify compute and text routes."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.pipeline.answer_verify import answers_equivalent
from src.pipeline.distractor_gate import stored_distractors_valid
from src.pipeline.answer_sympy_gate import enrich_distractor_latex, to_answer_latex
from src.pipeline.distractors import (
    generate_distractors,
    _minimum_distractor_count,
    _required_distractor_count,
)
from src.pipeline.deepseek_client import get_deepseek_model
from src.pipeline.models import ExtractedTask

log = logging.getLogger(__name__)

SUCCESS_STATUSES = frozenset({
    "verified_match",
    "verified_corrected",
    "generated_from_scratch",
})

MAX_DISTRACTOR_REGEN_ATTEMPTS = 5
MAX_FAILED_RETRY_ATTEMPTS = 5

# Shared SQL fragment: never re-queue tasks explicitly marked done or exhausted.
QUEUE_SKIP_SQL = """
  AND COALESCE(tm.tags->>'choices_complete', 'false') != 'true'
  AND COALESCE(tm.tags->>'distractor_locked', 'false') != 'true'
  AND COALESCE(tm.tags->>'distractor_regen_exhausted', 'false') != 'true'
  AND COALESCE(tm.tags->>'smart_verify_retry_exhausted', 'false') != 'true'
  AND COALESCE(tm.tags->>'needs_compound_split', 'false') != 'true'
  AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'
"""

TERMINAL_SKIP_STATUSES = frozenset({
    "verified_match",
    "verified_corrected",
    "generated_from_scratch",
    "needs_human_review",
    "needs_content_repair",
    "failed_at_llm",
    "failed_at_sympy",
})


def sync_verify_tags(tags: dict, status: str) -> None:
    tags["smart_verify_status"] = status
    tags["answer_verify_mode"] = status
    tags["smart_verify_at"] = datetime.now(timezone.utc).isoformat()
    tags["smart_verify_model"] = get_deepseek_model()


def clear_stale_verify_flags(tags: dict) -> None:
    for key in (
        "verify_unresolved",
        "verify_conflict",
        "answer_mismatch",
        "verify_reverted",
        "distractor_regen_pending",
        "smart_verify_error",
        # These are candidates from a previous failed/review run.  The current
        # successful run writes ``answer_llm_prose`` afresh, so retaining an
        # older candidate makes audit logs appear contradictory.
        "answer_gemini_candidate",
        "answer_gemini_flash",
        "answer_gemini_pro_candidate",
        "self_consistency_votes",
        "self_consistency_majority",
    ):
        tags.pop(key, None)


def verification_status(tags: dict) -> str:
    if (
        tags.get("smart_verify_status") in SUCCESS_STATUSES
        and tags.get("choices_complete") is True
        and not tags.get("distractor_regen_pending")
    ):
        return "verified"
    return "pending"


def pick_consensus_canonical(
    votes: list[str],
    answer_type: str,
) -> tuple[Optional[str], bool, list[str]]:
    """Majority vote among canonical answers."""
    if not votes:
        return None, False, []

    groups: list[list[str]] = []
    for v in votes:
        placed = False
        for grp in groups:
            if answers_equivalent(v, grp[0], answer_type):
                grp.append(v)
                placed = True
                break
        if not placed:
            groups.append([v])

    groups.sort(key=len, reverse=True)
    winner_grp = groups[0]
    winner = winner_grp[0]
    unanimous = len(groups) == 1
    majority = len(winner_grp) >= 2 and len(winner_grp) > (len(votes) // 2)
    if unanimous or majority:
        return winner, unanimous, votes
    return None, False, votes


def distractors_complete(
    dmeta: list | None,
    *,
    question: str = "",
    correct_answer: str = "",
    answer_type: str = "",
) -> bool:
    minimum = _minimum_distractor_count(
        correct_answer,
        answer_type,
        question,
    )
    return isinstance(dmeta, list) and len(dmeta) >= minimum


def distractors_valid(
    dmeta: list | None,
    *,
    question: str,
    correct_answer: str,
    answer_type: str,
) -> bool:
    return stored_distractors_valid(
        dmeta,
        question=question,
        correct_answer=correct_answer,
        answer_type=answer_type,
        min_count=_minimum_distractor_count(
            correct_answer,
            answer_type,
            question,
        ),
    )


def apply_distractors(
    *,
    task_id: str,
    question: str,
    final_answer: str,
    atype: str,
    dmeta: list,
    tags: dict,
    need_distractors: bool,
    answer_corrected: bool,
    action: str,
) -> tuple[list, dict, str]:
    target = _required_distractor_count(final_answer, atype, question)
    minimum = _minimum_distractor_count(final_answer, atype, question)
    prev_dmeta = list(dmeta)

    if not need_distractors:
        if distractors_valid(
            dmeta,
            question=question,
            correct_answer=final_answer,
            answer_type=atype,
        ):
            tags["choices_complete"] = True
            tags.pop("distractor_regen_pending", None)
        return dmeta, tags, action

    et = ExtractedTask(
        temp_id=task_id,
        question_text=question or "",
        answer_raw=final_answer,
        answer_type=atype,
        distractor_meta=dmeta if dmeta else None,
        tags=dict(tags),
    )
    result_et = generate_distractors(
        et,
        verify_answer=False,
        force_distractors=True,
    )
    tags.update(result_et.tags or {})
    generated = list(result_et.distractor_meta or [])
    got = len(generated)
    generated_valid = distractors_valid(
        generated,
        question=question,
        correct_answer=final_answer,
        answer_type=atype,
    )
    if got >= minimum and generated_valid:
        dmeta = result_et.distractor_meta[:target]
        tags["choices_complete"] = True
        tags.pop("distractor_regen_pending", None)
        if got < target:
            tags["distractor_count_partial"] = got
        action = f"{action}+new_dist"
    elif need_distractors:
        tags["choices_complete"] = False
        tags["distractor_regen_pending"] = True
        # Keep partial new dist or previous meta — never wipe to [] on failed regen.
        if got > 0:
            dmeta = list(result_et.distractor_meta or [])[:target]
        else:
            dmeta = prev_dmeta
        action = f"{action}+regen_pending"
    return dmeta, tags, action


def run_distractor_only_pipeline(
    *,
    task_id: str,
    question: str,
    correct_answer: str,
    answer_type: str,
    distractor_meta: list | None,
    tags: dict | None,
) -> dict[str, Any]:
    """Regenerate distractors only — skip LLM answer verification."""
    tags = dict(tags or {})
    dmeta = list(distractor_meta or [])
    atype = (answer_type or "exact_number").lower()
    stored = (correct_answer or "").strip()
    action = tags.get("smart_verify_status", "verified_match")

    if distractors_complete(
        dmeta,
        question=question,
        correct_answer=stored,
        answer_type=atype,
    ) and distractors_valid(
        dmeta,
        question=question,
        correct_answer=stored,
        answer_type=atype,
    ):
        dmeta = enrich_distractor_latex(dmeta, atype)
        tags["choices_complete"] = True
        tags.pop("distractor_regen_pending", None)
        return {
            "status": "success",
            "correct_answer": stored,
            "correct_answer_latex": to_answer_latex(stored, atype) if stored else "",
            "distractor_meta": dmeta[: _required_distractor_count(stored, atype, question)],
            "tags": tags,
            "action": f"{action}+dist_ok",
            "verification_status": verification_status(tags),
        }

    dmeta, tags, action = apply_distractors(
        task_id=task_id,
        question=question,
        final_answer=stored,
        atype=atype,
        dmeta=dmeta,
        tags=tags,
        need_distractors=True,
        answer_corrected=False,
        action=action,
    )

    if tags.get("distractor_regen_pending"):
        attempts = int(tags.get("distractor_regen_attempts", 0)) + 1
        tags["distractor_regen_attempts"] = attempts
        if attempts >= MAX_DISTRACTOR_REGEN_ATTEMPTS:
            tags["distractor_regen_exhausted"] = True
            tags.pop("distractor_regen_pending", None)
            action = f"{action}+regen_exhausted"
            log.warning(
                "Distractor regen exhausted %s after %d attempts",
                task_id,
                attempts,
            )

    dmeta = enrich_distractor_latex(dmeta, atype)
    calatex = to_answer_latex(stored, atype) if stored else ""

    return {
        "status": "success",
        "correct_answer": stored,
        "correct_answer_latex": calatex,
        "distractor_meta": dmeta,
        "tags": tags,
        "action": action,
        "verification_status": verification_status(tags),
    }


def bump_failed_retry_counter(tags: dict, prev_status: str, new_status: str) -> None:
    """Stop infinite retry loops for tasks that keep failing."""
    if new_status not in ("failed_at_llm", "failed_at_sympy"):
        tags.pop("smart_verify_retry_count", None)
        tags.pop("smart_verify_retry_exhausted", None)
        return
    if prev_status == new_status:
        count = int(tags.get("smart_verify_retry_count", 0)) + 1
        tags["smart_verify_retry_count"] = count
        if count >= MAX_FAILED_RETRY_ATTEMPTS:
            tags["smart_verify_retry_exhausted"] = True
            log.warning("Smart verify retry exhausted for status=%s after %d tries", new_status, count)
    else:
        tags["smart_verify_retry_count"] = 1
        tags.pop("smart_verify_retry_exhausted", None)
