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
from src.schemas.smart_verify import TextAnswerRelationResponse, TextVerifyResponse

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
        "Задача может быть текстовой, геометрической или логической.\n"
        "Не пиши ход решения, доказательство или объяснение. Верни только "
        "канонический итог: число с единицей, знак, да/нет, название объекта "
        "или краткий вывод.\n\n"
        f"ID: {task_id}\n"
        f"Вопрос:\n{question}\n\n"
        f"{alt_line}\n"
        "Верни JSON:\n"
        "- absolute_correct_answer: финальный ответ (кратко, школьная запись)\n"
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


def _build_text_source_relation_prompt(
    *,
    task_id: str,
    question: str,
    stored_answer: str,
    unanimous_candidate: str,
) -> str:
    """Ask only whether a source rewrite is warranted, never to re-solve.

    The candidate has already passed three independent, source-blind solves.
    This is not a fourth solver or a substitute for their consensus: it
    distinguishes a factual correction from a harmless rewording before a
    historical answer is overwritten.
    """
    return (
        "Ты — строгий редактор учебного контента. Не решай задачу заново и не "
        "придумывай новый ответ. Сравни смысл двух уже имеющихся ответов к "
        "одному вопросу.\n\n"
        f"ID: {task_id}\n"
        f"Вопрос:\n{question}\n\n"
        f"Исходный ответ:\n{stored_answer}\n\n"
        f"Единый ответ трёх независимых решателей:\n{unanimous_candidate}\n\n"
        "Выбери ровно одно значение relation:\n"
        "- equivalent — одинаковый смысл; отличаются только запись, падеж, "
        "порядок слов, единицы в равнозначной форме или пояснение.\n"
        "- candidate_corrects_source — ответы расходятся по факту, числу, "
        "объекту, знаку, условию или выводу; кандидат исправляет исходный.\n"
        "- inconclusive — из данных нельзя надёжно различить эти случаи.\n\n"
        "Верни только JSON с полем relation."
    )


def _compare_text_source_relation(
    *,
    task_id: str,
    question: str,
    stored_answer: str,
    unanimous_candidate: str,
) -> Optional[str]:
    """Return a safe source-write decision for a text consensus."""
    try:
        result = call_deepseek_structured(
            _build_text_source_relation_prompt(
                task_id=task_id,
                question=question,
                stored_answer=stored_answer,
                unanimous_candidate=unanimous_candidate,
            ),
            TextAnswerRelationResponse,
            model=get_deepseek_model(),
            temperature=0.0,
            max_tokens=200,
        )
        return result.relation
    except Exception as exc:
        log.warning("Text source comparison failed %s: %s", task_id, exc)
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
    preserve_source_on_mismatch: bool = False,
    require_unanimous_consensus: bool = False,
) -> dict[str, Any]:
    """Smart Verify for text / open_text / coordinate (prose answers).

    ``preserve_source_on_mismatch`` is for legacy records whose source type is
    known to be wrong.  Smart Verify may then verify an independently matched
    answer, but it must not replace the historical answer with a paraphrase or
    a single-model reconstruction.  A mismatch is retained for review with
    the candidate as evidence.
    """
    tags = dict(tags or {})
    dmeta = list(distractor_meta or [])
    atype = (answer_type or "text").lower().strip()
    stored = (correct_answer or "").strip() or None
    settings = get_settings()
    _ = answer_authority or settings.smart_verify_text_authority  # legacy param; no textbook branch

    tags["smart_verify_route"] = "text"

    local_sympy = compute_answer_from_question(question) if is_high_confidence_arithmetic(question) else None
    # An arbitration always gathers three independent model solutions for an
    # existing source answer — even when a quick local calculation happens to
    # match it. This prevents a one-pass confirmation from being mistaken for
    # the required three-way proof.
    if local_sympy and not require_unanimous_consensus:
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
            if preserve_source_on_mismatch:
                sync_verify_tags(tags, "needs_human_review")
                tags["answer_source_review_required"] = True
                tags["answer_gemini_candidate"] = local_sympy[:500]
                tags.pop("answer_gemini_verified", None)
                return {
                    "status": "review",
                    "correct_answer": stored,
                    "distractor_meta": dmeta,
                    "tags": tags,
                    "action": "needs_human_review_source_preserved",
                    "verification_status": "pending",
                }
            tags["answer_previous"] = stored
            tags.pop("verification_explanation", None)
            tags.pop("answer_verification_explanation", None)
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

    tags.pop("step_by_step_solution", None)
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

    if not has_old_answer and not require_unanimous_consensus:
        final_answer = computed
        sync_verify_tags(tags, "generated_from_scratch")
        need_distractors = True
        answer_corrected = True
    elif answers_equivalent(stored, computed, atype) and not require_unanimous_consensus:
        sync_verify_tags(tags, "verified_match")
        final_answer = stored
        need_distractors = not has_old_distractors
    else:
        votes = [computed]
        # A semantic arbitration is valid only with three independent solves.
        # Do not let an environment default such as ``1`` silently weaken it.
        n_runs = max(
            3 if require_unanimous_consensus else 1,
            settings.smart_verify_consistency_runs,
        )
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
        elif stored and answers_equivalent(stored, winner, atype, question=question):
            # Exact/deterministic equivalence needs no additional LLM call and
            # keeps the source representation unchanged.
            final_answer = stored
            sync_verify_tags(tags, "verified_match")
            need_distractors = not has_old_distractors
            tags["answer_format_preserved"] = True
        elif preserve_source_on_mismatch and not require_unanimous_consensus:
            # A one-pass recovery must never replace a historical prose
            # answer.  The three-answer route below is different: it has
            # independent agreement and still performs a source-aware
            # comparison before it writes anything.
            sync_verify_tags(tags, "needs_human_review")
            tags["answer_source_review_required"] = True
            tags["answer_gemini_candidate"] = winner[:500]
            tags.pop("answer_gemini_verified", None)
            return {
                "status": "review",
                "correct_answer": stored,
                "distractor_meta": dmeta,
                "tags": tags,
                "action": "needs_human_review_source_preserved",
                "verification_status": "pending",
            }
        elif require_unanimous_consensus and stored:
            # Three independent semantic answers are sufficient to certify a
            # source answer only when they are equivalent to it.  They are not
            # an oracle for replacing educational content: correlated model
            # mistakes can be unanimous (for example, by overlooking a domain
            # restriction in an identity).  Keep any factual disagreement as
            # review evidence and leave the source untouched.
            # The comparator may only establish harmless equivalence.  Its
            # result is deliberately one-directional: it can preserve the
            # source, but can never authorize replacing it.
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
        elif not (stored and answers_equivalent(stored, winner, atype, question=question)):
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
