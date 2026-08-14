"""MCQ Smart Verify — text/consensus route without SymPy code_execution."""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.core.config import get_settings
from src.pipeline.answer_verify import answers_equivalent
from src.pipeline.deepseek_client import call_deepseek_structured, get_deepseek_model
from src.pipeline.smart_verify_common import (
    SUCCESS_STATUSES,
    apply_distractors,
    clear_stale_verify_flags,
    distractors_valid,
    pick_consensus_canonical,
    sync_verify_tags,
    verification_status,
)
from src.pipeline.smart_verify_text import _compare_text_source_relation
from src.schemas.smart_verify import TextVerifyResponse

log = logging.getLogger(__name__)


def _build_mcq_prompt(
    task_id: str,
    question: str,
    stored_answer: Optional[str],
    *,
    alt_method: bool = False,
) -> str:
    alt_line = "\nПерепроверь другим способом.\n" if alt_method else ""
    return (
        "Ты — учитель математики. Задача с выбором / сравнением / да-нет.\n"
        "Решай по самому вопросу. Игнорируй любой уже сохранённый ответ: он может быть неверным или обрезанным.\n"
        "НЕ пиши код. Дай только финальный ответ в школьной записи.\n\n"
        f"ID: {task_id}\n"
        f"Вопрос:\n{question}\n\n"
        f"{alt_line}\n"
        "Правила ответа:\n"
        "- да / нет / буква варианта (а, б, в) / число / краткая фраза\n"
        "- несколько подпунктов (д), е), ж)): 'да; д) π; е) 3,(14)'\n"
        "- сохраняй метки подпунктов как в учебнике\n\n"
        "Верни JSON:\n"
        "- absolute_correct_answer\n"
        "- confidence: high | medium | low\n"
    )


def _run_mcq_llm(
    task_id: str,
    question: str,
    stored: Optional[str],
    *,
    alt_method: bool = False,
    temperature: float = 0.1,
) -> Optional[TextVerifyResponse]:
    try:
        return call_deepseek_structured(
            _build_mcq_prompt(task_id, question, stored, alt_method=alt_method),
            TextVerifyResponse,
            model=get_deepseek_model(),
            temperature=temperature,
        )
    except Exception as exc:
        log.warning("MCQ verify LLM failed %s: %s", task_id, exc)
        return None


def run_mcq_verify_pipeline(
    *,
    task_id: str,
    question: str,
    correct_answer: Optional[str],
    distractor_meta: Optional[list],
    tags: Optional[dict],
    answer_authority: Optional[str] = None,
    require_unanimous_consensus: bool = False,
) -> dict[str, Any]:
    """Smart Verify for multiple_choice (including compound д)/е) answers)."""
    tags = dict(tags or {})
    dmeta = list(distractor_meta or [])
    atype = "multiple_choice"
    stored = (correct_answer or "").strip() or None
    settings = get_settings()
    authority = answer_authority or settings.smart_verify_text_authority

    tags["smart_verify_route"] = "mcq_text"

    llm_result = _run_mcq_llm(task_id, question, stored, alt_method=False, temperature=0.0)
    if llm_result is None:
        sync_verify_tags(tags, "failed_at_llm")
        tags["smart_verify_error"] = "mcq_llm_failed"
        tags.pop("answer_gemini_verified", None)
        return {
            "status": "error",
            "correct_answer": stored or "",
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "failed_at_llm",
            "verification_status": "pending",
        }

    computed = (llm_result.absolute_correct_answer or "").strip()
    if not computed:
        sync_verify_tags(tags, "failed_at_llm")
        tags["smart_verify_error"] = "empty_mcq_answer"
        return {
            "status": "error",
            "correct_answer": stored or "",
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "failed_at_llm",
            "verification_status": "pending",
        }

    tags.pop("step_by_step_solution", None)
    tags["text_verify_confidence"] = llm_result.confidence
    tags["answer_llm_prose"] = computed[:500]
    tags["answer_canonical_source"] = "mcq_llm"
    tags["sympy_gate_reason"] = "mcq_text_route"

    has_old_answer = bool(stored)
    has_old_distractors = distractors_valid(
        dmeta,
        question=question,
        correct_answer=stored or "",
        answer_type=atype,
    )
    need_distractors = False
    answer_corrected = False
    final_answer = computed

    if not has_old_answer and not require_unanimous_consensus:
        final_answer = computed
        sync_verify_tags(tags, "generated_from_scratch")
        need_distractors = True
        answer_corrected = True
    elif answers_equivalent(
        stored, computed, atype, question=question,
    ) and not require_unanimous_consensus:
        sync_verify_tags(tags, "verified_match")
        final_answer = stored
        need_distractors = not has_old_distractors
        tags["answer_format_preserved"] = True
    else:
        if authority == "textbook" and not require_unanimous_consensus:
            sync_verify_tags(tags, "needs_human_review")
            tags["answer_gemini_candidate"] = computed[:500]
            tags.pop("answer_gemini_verified", None)
            return {
                "status": "review",
                "correct_answer": stored,
                "distractor_meta": dmeta,
                "tags": tags,
                "action": "needs_human_review",
                "verification_status": "pending",
            }

        votes = [computed]
        # Multiple-choice / yes-no answers have no SymPy proof path.  In
        # arbitration mode their authority is exactly three unanimous,
        # independent model answers.
        n_runs = max(
            3 if require_unanimous_consensus else 1,
            settings.smart_verify_consistency_runs,
        )
        for _ in range(n_runs - 1):
            llm2 = _run_mcq_llm(
                task_id, question, stored,
                alt_method=True,
                temperature=settings.smart_verify_consistency_temperature,
            )
            if llm2 and (llm2.absolute_correct_answer or "").strip():
                votes.append(llm2.absolute_correct_answer.strip())

        tags["self_consistency_votes"] = votes[:10]
        winner, unanimous, _ = pick_consensus_canonical(votes, atype)
        if require_unanimous_consensus:
            tags["smart_verify_consensus_required"] = n_runs
            tags["smart_verify_consensus_obtained"] = len(votes)
            tags["smart_verify_consensus_unanimous"] = bool(
                len(votes) >= n_runs and unanimous
            )
            if len(votes) < n_runs or not unanimous:
                sync_verify_tags(tags, "needs_human_review")
                tags["smart_verify_arbitration_reason"] = "non_unanimous_consensus"
                tags["answer_gemini_candidate"] = computed[:500]
                tags.pop("answer_gemini_verified", None)
                return {
                    "status": "review",
                    "correct_answer": stored,
                    "distractor_meta": dmeta,
                    "tags": tags,
                    "action": "needs_human_review_non_unanimous_consensus",
                    "verification_status": "pending",
                }
        if winner is None:
            sync_verify_tags(tags, "needs_human_review")
            tags["answer_gemini_candidate"] = computed[:500]
            tags.pop("answer_gemini_verified", None)
            return {
                "status": "review",
                "correct_answer": stored,
                "distractor_meta": dmeta,
                "tags": tags,
                "action": "needs_human_review",
                "verification_status": "pending",
            }

        if not has_old_answer:
            final_answer = winner
            sync_verify_tags(tags, "generated_from_scratch")
            dmeta = []
            need_distractors = True
            answer_corrected = True
        elif answers_equivalent(stored, winner, atype, question=question):
            sync_verify_tags(tags, "verified_match")
            final_answer = stored
            need_distractors = not has_old_distractors
            tags["answer_format_preserved"] = True
        elif require_unanimous_consensus and stored:
            # Three model solves can confirm an existing choice only when it
            # already matches the source. A mismatch is review evidence, not
            # permission to overwrite the educational truth value.
            # This comparison can only confirm a cosmetic equivalence and
            # preserve the source. It can never authorize a source rewrite.
            source_relation = _compare_text_source_relation(
                task_id=task_id,
                question=question,
                stored_answer=stored,
                unanimous_candidate=winner,
            )
            tags["smart_verify_text_source_relation"] = (
                source_relation or "inconclusive"
            )
            if source_relation == "equivalent":
                final_answer = stored
                sync_verify_tags(tags, "verified_match")
                need_distractors = not has_old_distractors
                tags["answer_format_preserved"] = True
            else:
                sync_verify_tags(tags, "needs_human_review")
                tags["smart_verify_arbitration_reason"] = (
                    "text_source_mismatch_requires_review"
                )
                tags["answer_source_review_required"] = True
                tags["answer_gemini_candidate"] = winner[:500]
                tags.pop("answer_gemini_verified", None)
                return {
                    "status": "review",
                    "correct_answer": stored,
                    "distractor_meta": dmeta,
                    "tags": tags,
                    "action": "needs_human_review_text_source_mismatch",
                    "verification_status": "pending",
                }
        else:
            tags["answer_previous"] = stored
            tags.pop("verification_explanation", None)
            tags.pop("answer_verification_explanation", None)
            final_answer = winner
            sync_verify_tags(tags, "verified_corrected")
            if not unanimous:
                tags["self_consistency_majority"] = True
            dmeta = []
            need_distractors = True
            answer_corrected = True

    if tags.get("smart_verify_status") in SUCCESS_STATUSES:
        clear_stale_verify_flags(tags)
        if require_unanimous_consensus:
            tags["smart_verify_arbitration_votes"] = votes[:10]
        tags["answer_gemini_verified"] = True
        tags["answer_locked"] = True
        tags["answer_source"] = (
            "computed" if answer_corrected and has_old_answer
            else "textbook" if has_old_answer else "computed"
        )

    action = tags.get("smart_verify_status", "unknown")
    dmeta, tags, action = apply_distractors(
        task_id=task_id,
        question=question,
        final_answer=final_answer,
        atype=atype,
        dmeta=dmeta,
        tags=tags,
        need_distractors=need_distractors,
        answer_corrected=answer_corrected,
        action=action,
    )

    return {
        "status": "success",
        "correct_answer": final_answer,
        "correct_answer_latex": "",
        "distractor_meta": dmeta,
        "tags": tags,
        "action": action,
        "verification_status": verification_status(tags),
    }
