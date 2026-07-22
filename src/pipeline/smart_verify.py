"""
Smart Verify pipeline — isolated compute (code_execution) + distractor generation.

Strict rule: answer verification and distractor generation are NEVER combined in one LLM call.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import (
    SMART_VERIFY_TYPES,
    SympyGateResult,
    beautify_answer_if_equivalent,
    enrich_distractor_latex,
    resolve_canonical_answer,
    sympy_gate,
    to_answer_latex,
)
from src.pipeline.answer_verify import answers_equivalent, stored_answer_matches_compute
from src.pipeline.deepseek_client import call_deepseek_code_execution
from src.pipeline.smart_verify_common import (
    SUCCESS_STATUSES,
    TERMINAL_SKIP_STATUSES,
    apply_distractors,
    clear_stale_verify_flags,
    distractors_complete,
    distractors_valid,
    pick_consensus_canonical,
    sync_verify_tags,
    verification_status,
)
from src.pipeline.compound_detect import apply_compound_tags, detect_compound
from src.pipeline.smart_verify_mcq import run_mcq_verify_pipeline
from src.pipeline.smart_verify_text import TEXT_VERIFY_TYPES, run_text_verify_pipeline
from src.schemas.smart_verify import SmartVerifyResponse

log = logging.getLogger(__name__)

# Re-export for scripts that import from smart_verify
__all__ = [
    "SUCCESS_STATUSES",
    "TERMINAL_SKIP_STATUSES",
    "run_smart_verify_pipeline",
]


def _build_compute_prompt(
    task_id: str,
    question: str,
    answer_type: str,
    stored_answer: Optional[str],  # kept in signature for compat, but NOT used in prompt
    *,
    alt_method: bool = False,
) -> str:
    # ВАЖНО: stored_answer намеренно НЕ передаётся в промпт.
    # LLM должна решать задачу независимо, без "якорения" на ответ из учебника.
    # Сравнение с учебником происходит ПОСЛЕ независимого вычисления.
    alt_line = (
        "\nРеши задачу другим методом (другой подход, другое разложение и т.п.).\n"
        if alt_method else ""
    )
    return (
        "Ты — точный математический решатель. Реши задачу с помощью Python/SymPy.\n"
        "НЕ рассуждай вслух. Напиши только Python-код с результатом.\n\n"
        f"ID задачи: {task_id}\n"
        f"Тип ответа: {answer_type}\n"
        f"Текст задачи:\n{question}\n\n"
        f"{alt_line}"
        "Код должен присвоить переменной `result` словарь с ключами:\n"
        "- sympy_compatible_string: SymPy-выражение (напр. Eq(2*x-4, 10) или solve(...))\n"
        "- absolute_correct_answer: финальный ответ в школьной записи (только значение)\n"
        "- step_by_step_solution: краткое пошаговое решение для ученика\n\n"
        "Для нескольких корней используй '; ' как разделитель.\n"
        "Верни ТОЛЬКО блок ```python ... ``` без пояснений."
    )



def _error_result(
    *,
    tags: dict,
    status_key: str,
    action: str,
    stored: Optional[str],
    dmeta: list,
    error: str = "",
    extra_tags: Optional[dict] = None,
) -> dict[str, Any]:
    sync_verify_tags(tags, status_key)
    if error:
        tags["smart_verify_error"] = error[:300]
    tags.pop("answer_gemini_verified", None)
    if extra_tags:
        tags.update(extra_tags)
    return {
        "status": "error" if status_key.startswith("failed") else "review",
        "correct_answer": stored or "",
        "distractor_meta": dmeta,
        "tags": tags,
        "action": action,
        "verification_status": "pending",
    }


def _run_single_compute(
    task_id: str,
    question: str,
    atype: str,
    stored: Optional[str],
    *,
    alt_method: bool = False,
    temperature: float = 0.0,
) -> tuple[Optional[SmartVerifyResponse], Optional[SympyGateResult], Optional[str]]:
    """One code_execution run + gate. Returns (llm_result, gate, canonical)."""
    try:
        llm_result = call_deepseek_code_execution(
            _build_compute_prompt(task_id, question, atype, stored, alt_method=alt_method),
            schema=SmartVerifyResponse,
            temperature=temperature,
        )
    except Exception as exc:
        log.warning("Smart verify LLM failed %s: %s", task_id, exc)
        return None, None, None

    computed_answer = (llm_result.absolute_correct_answer or "").strip()
    if not computed_answer:
        return llm_result, None, None

    gate = sympy_gate(
        llm_result.sympy_compatible_string,
        computed_answer,
        atype,
        question=question,
        stored_answer=stored or "",
    )
    if not gate.ok:
        return llm_result, gate, None

    canonical, _source = resolve_canonical_answer(
        gate,
        computed_answer,
        question=question,
        answer_type=atype,
        sympy_string=llm_result.sympy_compatible_string,
    )
    return llm_result, gate, canonical


def run_smart_verify_pipeline(
    *,
    task_id: str,
    question: str,
    correct_answer: Optional[str],
    answer_type: str,
    distractor_meta: Optional[list],
    tags: Optional[dict],
    answer_authority: Optional[str] = None,
) -> dict[str, Any]:
    """
    Smart Verify for one task (compute or text route).

    Returns dict with keys: status, correct_answer, distractor_meta, tags, action.
    """
    tags = dict(tags or {})
    dmeta = list(distractor_meta or [])
    atype = (answer_type or "exact_number").lower().strip()
    stored = (correct_answer or "").strip() or None
    authority = answer_authority or get_settings().smart_verify_answer_authority

    # ── Early-exit guard ────────────────────────────────────────────────────────
    # If this task was already locked by a previous smart-verify pass, skip the
    # expensive LLM compute entirely.  Only regenerate distractors if missing.
    #
    # Two signals are treated as "locked":
    #   1. answer_locked=True + answer_gemini_verified=True + SUCCESS status  (smart_verify path)
    #   2. reverified_by='deepseek_school' + choices_complete=True
    #      AND verify_mode is not a failure mode  (force_resolve path)
    #
    # IMPORTANT: failed tasks (unresolved, dual_failed, stored_invalid, failed_at_*)
    # are NEVER locked — they must always be retried by the next pass.
    _FAILED_MODES = frozenset({
        "unresolved", "dual_failed", "stored_invalid",
        "failed_at_llm", "failed_at_sympy",
    })
    _verify_mode = tags.get("answer_verify_mode") or ""
    _is_smart_locked = (
        tags.get("answer_locked")
        and tags.get("answer_gemini_verified")
        and tags.get("smart_verify_status") in SUCCESS_STATUSES
        and _verify_mode not in _FAILED_MODES
    )
    _is_school_locked = (
        tags.get("reverified_by") == "deepseek_school"
        and tags.get("choices_complete")
        and _verify_mode not in _FAILED_MODES
    )
    if _is_smart_locked or _is_school_locked:
        has_old_distractors = distractors_valid(
            dmeta,
            question=question,
            correct_answer=stored or "",
            answer_type=atype,
        )
        if has_old_distractors:
            # Nothing to do — fully complete.
            return {
                "status": "success",
                "correct_answer": stored or "",
                "correct_answer_latex": to_answer_latex(stored or "", atype),
                "distractor_meta": dmeta,
                "tags": tags,
                "action": "already_locked_skip",
                "verification_status": "verified",
            }
        # Distractors missing — regenerate without touching the answer.
        from src.pipeline.smart_verify_common import run_distractor_only_pipeline
        return run_distractor_only_pipeline(
            task_id=task_id,
            question=question,
            correct_answer=stored or "",
            answer_type=atype,
            distractor_meta=dmeta,
            tags=tags,
        )
    # ── End early-exit guard ────────────────────────────────────────────────────

    compound = detect_compound(
        task_id=task_id,
        question_text=question or "",
        correct_answer=stored or "",
        answer_type=atype,
        tags=tags,
    )
    if compound.should_split and compound.exam_unsafe:
        tags = apply_compound_tags(tags, compound)
        sync_verify_tags(tags, "needs_compound_split")
        tags["smart_verify_error"] = compound.warning[:300]
        log.warning("Compound unsplit %s: %s", task_id, compound.warning)
        return {
            "status": "skipped",
            "correct_answer": stored or "",
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "needs_compound_split",
            "verification_status": "pending",
        }

    if atype == "multiple_choice":
        return run_mcq_verify_pipeline(
            task_id=task_id,
            question=question,
            correct_answer=correct_answer,
            distractor_meta=dmeta,
            tags=tags,
            answer_authority=answer_authority,
        )

    if atype in TEXT_VERIFY_TYPES or atype == "coordinate":
        return run_text_verify_pipeline(
            task_id=task_id,
            question=question,
            correct_answer=correct_answer,
            answer_type=atype,
            distractor_meta=dmeta,
            tags=tags,
            answer_authority=answer_authority,
        )

    if atype not in SMART_VERIFY_TYPES:
        tags["smart_verify_status"] = "skipped_type"
        tags["answer_verify_mode"] = "skipped_type"
        return {
            "status": "skipped",
            "correct_answer": stored or "",
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "skipped_type",
            "verification_status": verification_status(tags),
        }

    llm_result, gate, canonical = _run_single_compute(
        task_id, question, atype, stored, alt_method=False, temperature=0.0,
    )
    if llm_result is None:
        return _error_result(
            tags=tags, status_key="failed_at_llm", action="failed_at_llm",
            stored=stored, dmeta=dmeta, error="gemini_code_execution_failed",
        )
    if gate is None:
        return _error_result(
            tags=tags, status_key="failed_at_llm", action="failed_at_llm",
            stored=stored, dmeta=dmeta, error="empty absolute_correct_answer",
        )
    if not gate.ok:
        log.info(
            "Smart verify SymPy gate failed %s: %s (local=%r)",
            task_id, gate.reason, gate.computed_local,
        )
        return _error_result(
            tags=tags, status_key="failed_at_sympy", action="failed_at_sympy",
            stored=stored, dmeta=dmeta, error=gate.reason,
            extra_tags={
                "sympy_compatible_string": llm_result.sympy_compatible_string[:500],
                "answer_gemini_candidate": (llm_result.absolute_correct_answer or "")[:500],
            },
        )

    llm_prose = (llm_result.absolute_correct_answer or "").strip()
    canonical_source = resolve_canonical_answer(
        gate, llm_prose, question=question, answer_type=atype,
        sympy_string=llm_result.sympy_compatible_string,
    )[1]
    tags["answer_llm_prose"] = llm_prose[:500]
    tags["answer_canonical_source"] = canonical_source
    tags["sympy_compatible_string"] = llm_result.sympy_compatible_string[:500]
    tags["step_by_step_solution"] = llm_result.step_by_step_solution[:2000]

    has_old_answer = bool(stored)
    has_old_distractors = distractors_valid(
        dmeta,
        question=question,
        correct_answer=stored or "",
        answer_type=atype,
    )
    need_distractors = False
    answer_corrected = False
    final_answer = canonical or llm_prose

    if not has_old_answer:
        final_answer = canonical or llm_prose
        sync_verify_tags(tags, "generated_from_scratch")
        need_distractors = True
        answer_corrected = True
    elif stored_answer_matches_compute(
        stored,
        final_answer,
        gate.computed_local or "",
        llm_prose,
        answer_type=atype,
    ):
        sync_verify_tags(tags, "verified_match")
        final_answer = stored
        need_distractors = not has_old_distractors
        tags["answer_format_preserved"] = True
    else:
        if authority == "textbook":
            sync_verify_tags(tags, "needs_human_review")
            tags["answer_gemini_candidate"] = final_answer[:500]
            tags.pop("answer_gemini_verified", None)
            return {
                "status": "review",
                "correct_answer": stored,
                "correct_answer_latex": to_answer_latex(stored or "", atype),
                "distractor_meta": dmeta,
                "tags": tags,
                "action": "needs_human_review",
                "verification_status": "pending",
            }

        settings = get_settings()
        votes = [final_answer]
        n_runs = max(1, settings.smart_verify_consistency_runs)
        for _ in range(n_runs - 1):
            _llm2, gate2, canon2 = _run_single_compute(
                task_id, question, atype, stored,
                alt_method=True,
                temperature=settings.smart_verify_consistency_temperature,
            )
            if gate2 and gate2.ok and canon2:
                votes.append(canon2)

        tags["self_consistency_votes"] = votes[:10]
        winner, unanimous, _all = pick_consensus_canonical(votes, atype)
        if winner is None:
            sync_verify_tags(tags, "needs_human_review")
            tags["answer_gemini_candidate"] = final_answer[:500]
            tags.pop("answer_gemini_verified", None)
            return {
                "status": "review",
                "correct_answer": stored,
                "correct_answer_latex": to_answer_latex(stored or "", atype),
                "distractor_meta": dmeta,
                "tags": tags,
                "action": "needs_human_review",
                "verification_status": "pending",
            }

        if stored_answer_matches_compute(stored, winner, answer_type=atype):
            sync_verify_tags(tags, "verified_match")
            final_answer = stored
            need_distractors = not has_old_distractors
            tags["answer_format_preserved"] = True
        else:
            tags["answer_previous"] = stored
            final_answer = winner
            sync_verify_tags(tags, "verified_corrected")
            if not unanimous:
                tags["self_consistency_majority"] = True
            dmeta = []
            need_distractors = True
            answer_corrected = True

    if tags.get("smart_verify_status") not in ("needs_human_review",):
        clear_stale_verify_flags(tags)
        tags["answer_gemini_verified"] = True
        tags["answer_locked"] = True
        tags["sympy_gate_reason"] = gate.reason
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

    if atype in ("expression", "fraction"):
        final_answer = beautify_answer_if_equivalent(final_answer, atype)

    dmeta = enrich_distractor_latex(dmeta, atype)
    correct_answer_latex = to_answer_latex(final_answer, atype)

    return {
        "status": "success",
        "correct_answer": final_answer,
        "correct_answer_latex": correct_answer_latex,
        "distractor_meta": dmeta,
        "tags": tags,
        "action": action,
        "verification_status": verification_status(tags),
    }
