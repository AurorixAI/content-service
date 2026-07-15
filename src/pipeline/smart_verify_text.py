"""Text-route Smart Verify — local SymPy first, then LLM (no textbook authority)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.core.config import get_settings
from src.pipeline.arith_from_question import compute_answer_from_question, is_high_confidence_arithmetic
from src.pipeline.answer_verify import answers_equivalent
from src.pipeline.deepseek_client import call_deepseek_structured, get_deepseek_model
from src.pipeline.smart_verify_common import (
    SUCCESS_STATUSES,
    apply_distractors,
    clear_stale_verify_flags,
    distractors_complete,
    distractors_valid,
    pick_consensus_canonical,
    sync_verify_tags,
    verification_status,
)
from src.schemas.smart_verify import TextVerifyResponse

log = logging.getLogger(__name__)

TEXT_VERIFY_TYPES = frozenset({"text", "open_text"})


def _build_text_prompt(
    task_id: str,
    question: str,
    stored_answer: Optional[str],  # kept in signature for compat, NOT used in prompt
    *,
    alt_method: bool = False,
) -> str:
    # ВАЖНО: stored_answer намеренно НЕ передаётся в промпт.
    # LLM решает задачу независимо — без "якорения" на ответ учебника.
    alt_line = "\nПерепроверь логику другим способом рассуждения.\n" if alt_method else ""
    return (
        "Ты — опытный учитель математики. Реши задачу и дай краткий точный ответ.\n"
        "Решай только по вопросу. Не опирайся на какой-либо предварительно сохранённый ответ — он может быть неверным, обрезанным или отсутствовать.\n"
        "Задача может быть текстовой, геометрической или логической.\n\n"
        f"ID: {task_id}\n"
        f"Вопрос:\n{question}\n\n"
        f"{alt_line}\n"
        "Верни JSON:\n"
        "- absolute_correct_answer: финальный ответ (кратко, школьная запись)\n"
        "- step_by_step_solution: краткое пошаговое обоснование\n"
        "- confidence: high | medium | low\n"
    )



def _run_text_llm(
    task_id: str,
    question: str,
    stored: Optional[str],
    *,
    alt_method: bool = False,
    temperature: float = 0.1,
) -> Optional[TextVerifyResponse]:
    try:
        return call_deepseek_structured(
            _build_text_prompt(task_id, question, stored, alt_method=alt_method),
            TextVerifyResponse,
            model=get_deepseek_model(),
            temperature=temperature,
        )
    except Exception as exc:
        log.warning("Text verify LLM failed %s: %s", task_id, exc)
        return None


def run_text_verify_pipeline(
    *,
    task_id: str,
    question: str,
    correct_answer: Optional[str],
    answer_type: str,
    distractor_meta: Optional[list],
    tags: Optional[dict],
    answer_authority: Optional[str] = None,
) -> dict[str, Any]:
    """Smart Verify for text / open_text / coordinate (prose answers)."""
    tags = dict(tags or {})
    dmeta = list(distractor_meta or [])
    atype = (answer_type or "text").lower().strip()
    stored = (correct_answer or "").strip() or None
    settings = get_settings()
    _ = answer_authority or settings.smart_verify_text_authority  # legacy param; no textbook branch

    tags["smart_verify_route"] = "text"

    local_sympy = compute_answer_from_question(question) if is_high_confidence_arithmetic(question) else None
    if local_sympy:
        tags["answer_local_sympy"] = local_sympy[:500]
        tags["answer_canonical_source"] = "local_sympy"
        has_old_answer = bool(stored)
        has_old_distractors = distractors_valid(
            dmeta,
            question=question,
            correct_answer=stored or local_sympy,
            answer_type=atype,
        )
        need_distractors = False
        answer_corrected = False

        if not has_old_answer:
            final_answer = local_sympy
            sync_verify_tags(tags, "generated_from_scratch")
            need_distractors = True
            answer_corrected = True
        elif answers_equivalent(stored, local_sympy, atype, question=question):
            sync_verify_tags(tags, "verified_match")
            final_answer = stored
            need_distractors = not has_old_distractors
        else:
            tags["answer_previous"] = stored
            final_answer = local_sympy
            sync_verify_tags(tags, "verified_corrected")
            dmeta = []
            need_distractors = True
            answer_corrected = True

        if tags.get("smart_verify_status") in SUCCESS_STATUSES:
            clear_stale_verify_flags(tags)
            tags["answer_gemini_verified"] = True
            tags["answer_locked"] = True
            tags["answer_source"] = "local_sympy"
            tags["sympy_gate_reason"] = "text_route_local_sympy"

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
            "distractor_meta": dmeta,
            "tags": tags,
            "action": action,
            "verification_status": verification_status(tags),
        }

    llm_result = _run_text_llm(task_id, question, stored, alt_method=False, temperature=0.1)
    if llm_result is None:
        sync_verify_tags(tags, "failed_at_llm")
        tags["smart_verify_error"] = "text_llm_failed"
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
        tags["smart_verify_error"] = "empty_text_answer"
        return {
            "status": "error",
            "correct_answer": stored or "",
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "failed_at_llm",
            "verification_status": "pending",
        }

    tags["step_by_step_solution"] = llm_result.step_by_step_solution[:2000]
    tags["text_verify_confidence"] = llm_result.confidence
    tags["answer_llm_prose"] = computed[:500]
    tags["answer_canonical_source"] = "text_llm"

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

    if not has_old_answer:
        final_answer = computed
        sync_verify_tags(tags, "generated_from_scratch")
        need_distractors = True
        answer_corrected = True
    elif answers_equivalent(stored, computed, atype):
        sync_verify_tags(tags, "verified_match")
        final_answer = stored
        need_distractors = not has_old_distractors
    else:
        votes = [computed]
        n_runs = max(1, settings.smart_verify_consistency_runs)
        for _ in range(n_runs - 1):
            llm2 = _run_text_llm(
                task_id, question, stored,
                alt_method=True,
                temperature=settings.smart_verify_consistency_temperature,
            )
            if llm2 and (llm2.absolute_correct_answer or "").strip():
                votes.append(llm2.absolute_correct_answer.strip())

        tags["self_consistency_votes"] = votes[:10]
        winner, unanimous, _ = pick_consensus_canonical(votes, atype)
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

        tags["answer_previous"] = stored
        final_answer = winner
        sync_verify_tags(tags, "verified_corrected")
        if not unanimous:
            tags["self_consistency_majority"] = True
        dmeta = []
        need_distractors = True
        answer_corrected = True

    if tags.get("smart_verify_status") in SUCCESS_STATUSES:
        clear_stale_verify_flags(tags)
        tags["answer_gemini_verified"] = True
        tags["answer_locked"] = True
        tags["answer_source"] = "computed" if answer_corrected or not has_old_answer else "llm_verified"
        tags["sympy_gate_reason"] = "text_route"

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
        "distractor_meta": dmeta,
        "tags": tags,
        "action": action,
        "verification_status": verification_status(tags),
    }
