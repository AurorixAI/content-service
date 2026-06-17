"""
Smart Verify pipeline — isolated compute (code_execution) + distractor generation.

Strict rule: answer verification and distractor generation are NEVER combined in one LLM call.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import SMART_VERIFY_TYPES, sympy_gate
from src.pipeline.answer_verify import answers_equivalent
from src.pipeline.distractors import generate_distractors
from src.pipeline.gemini_client import call_gemini_code_execution, get_flash_model
from src.pipeline.models import ExtractedTask
from src.schemas.smart_verify import SmartVerifyResponse

log = logging.getLogger(__name__)

SUCCESS_STATUSES = frozenset({
    "verified_match",
    "verified_corrected",
    "generated_from_scratch",
})

TERMINAL_SKIP_STATUSES = frozenset({
    "verified_match",
    "verified_corrected",
    "generated_from_scratch",
    "needs_human_review",
    "failed_at_llm",
    "failed_at_sympy",
})


def _build_compute_prompt(
    task_id: str,
    question: str,
    answer_type: str,
    stored_answer: Optional[str],
) -> str:
    stored_line = (
        f"Текущий ответ в базе (для сверки, не обязателен к копированию): {stored_answer}\n"
        if stored_answer
        else ""
    )
    return (
        "Ты — точный математический парсер и калькулятор.\n"
        "ЗАПРЕЩЕНО рассуждать вслух. Напиши и выполни Python-код (SymPy) для решения задачи.\n\n"
        f"ID задачи: {task_id}\n"
        f"Тип ответа: {answer_type}\n"
        f"Текст задачи:\n{question}\n\n"
        f"{stored_line}\n"
        "Верни СТРОГО JSON с полями:\n"
        "- sympy_compatible_string: выражение SymPy (например Eq(2*x-4, 10) или simplify(...))\n"
        "- absolute_correct_answer: финальный ответ в школьной записи (только значение)\n"
        "- step_by_step_solution: краткое пошаговое решение для ученика\n\n"
        "Для нескольких подответов используй разделитель '; '.\n"
        "Только JSON, без markdown."
    )


def _sync_verify_tags(tags: dict, status: str) -> None:
    """Keep legacy answer_verify_mode in sync for export/audit scripts."""
    tags["smart_verify_status"] = status
    tags["answer_verify_mode"] = status
    tags["smart_verify_at"] = datetime.now(timezone.utc).isoformat()
    tags["smart_verify_model"] = get_flash_model()


def _clear_stale_verify_flags(tags: dict) -> None:
    for key in (
        "verify_unresolved",
        "verify_conflict",
        "answer_mismatch",
        "verify_reverted",
        "distractor_regen_pending",
    ):
        tags.pop(key, None)


def _verification_status(tags: dict) -> str:
    if tags.get("smart_verify_status") in SUCCESS_STATUSES:
        return "verified"
    return "pending"


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
    Two-stage Smart Verify for one task.

    Returns dict with keys: status, correct_answer, distractor_meta, tags, action.
    """
    tags = dict(tags or {})
    dmeta = list(distractor_meta or [])
    atype = (answer_type or "exact_number").lower().strip()
    stored = (correct_answer or "").strip() or None
    authority = answer_authority or get_settings().smart_verify_answer_authority

    if atype not in SMART_VERIFY_TYPES:
        tags["smart_verify_status"] = "skipped_type"
        tags["answer_verify_mode"] = "skipped_type"
        return {
            "status": "skipped",
            "correct_answer": stored or "",
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "skipped_type",
            "verification_status": _verification_status(tags),
        }

    # ── Stage 1: LLM compute (code_execution) ─────────────────────────────
    try:
        llm_result = call_gemini_code_execution(
            _build_compute_prompt(task_id, question, atype, stored),
            schema=SmartVerifyResponse,
        )
    except Exception as exc:
        log.warning("Smart verify LLM failed %s: %s", task_id, exc)
        _sync_verify_tags(tags, "failed_at_llm")
        tags["smart_verify_error"] = str(exc)[:300]
        tags.pop("answer_gemini_verified", None)
        return {
            "status": "error",
            "correct_answer": stored or "",
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "failed_at_llm",
            "verification_status": "pending",
        }

    computed_answer = (llm_result.absolute_correct_answer or "").strip()
    if not computed_answer:
        _sync_verify_tags(tags, "failed_at_llm")
        tags["smart_verify_error"] = "empty absolute_correct_answer"
        return {
            "status": "error",
            "correct_answer": stored or "",
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "failed_at_llm",
            "verification_status": "pending",
        }

    # ── Stage 2: Local SymPy gate ─────────────────────────────────────────
    gate = sympy_gate(
        llm_result.sympy_compatible_string,
        computed_answer,
        atype,
        question=question,
        stored_answer=stored or "",
    )
    if not gate.ok:
        log.info(
            "Smart verify SymPy gate failed %s: %s (local=%r)",
            task_id, gate.reason, gate.computed_local,
        )
        _sync_verify_tags(tags, "failed_at_sympy")
        tags["smart_verify_error"] = gate.reason[:300]
        tags["sympy_compatible_string"] = llm_result.sympy_compatible_string[:500]
        tags["answer_gemini_candidate"] = computed_answer[:500]
        tags.pop("answer_gemini_verified", None)
        return {
            "status": "error",
            "correct_answer": stored or "",
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "failed_at_sympy",
            "verification_status": "pending",
        }

    # ── Stage 3: Routing (match / correct / scratch / human) ──────────────
    has_old_answer = bool(stored)
    has_old_distractors = bool(dmeta)
    need_distractors = False
    answer_corrected = False
    final_answer = stored or computed_answer

    if not has_old_answer:
        final_answer = computed_answer
        _sync_verify_tags(tags, "generated_from_scratch")
        need_distractors = True
        answer_corrected = True
    elif answers_equivalent(stored, computed_answer, atype):
        _sync_verify_tags(tags, "verified_match")
        need_distractors = not has_old_distractors
    else:
        # Mismatch textbook vs computed
        if authority == "textbook":
            _sync_verify_tags(tags, "needs_human_review")
            tags["answer_gemini_candidate"] = computed_answer[:500]
            tags["sympy_compatible_string"] = llm_result.sympy_compatible_string[:500]
            tags["step_by_step_solution"] = llm_result.step_by_step_solution[:2000]
            tags.pop("answer_gemini_verified", None)
            return {
                "status": "review",
                "correct_answer": stored,
                "distractor_meta": dmeta,
                "tags": tags,
                "action": "needs_human_review",
                "verification_status": "pending",
            }

        if authority == "ai_if_sympy_confirms":
            # Gate already passed — safe to correct
            pass
        # ai_first or ai_if_sympy_confirms → overwrite
        tags["answer_previous"] = stored
        final_answer = computed_answer
        _sync_verify_tags(tags, "verified_corrected")
        dmeta = []
        need_distractors = True
        answer_corrected = True

    if tags.get("smart_verify_status") not in ("needs_human_review",):
        _clear_stale_verify_flags(tags)
        tags["sympy_compatible_string"] = llm_result.sympy_compatible_string[:500]
        tags["step_by_step_solution"] = llm_result.step_by_step_solution[:2000]
        tags["answer_gemini_verified"] = True
        tags["answer_locked"] = True
        tags["sympy_gate_reason"] = gate.reason
        tags["answer_source"] = "computed" if answer_corrected and has_old_answer else (
            "textbook" if has_old_answer else "computed"
        )

    action = tags.get("smart_verify_status", "unknown")

    # ── Stage 4: Isolated distractor generation (teacher LLM only) ────────
    if need_distractors:
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
        if result_et.distractor_meta:
            dmeta = result_et.distractor_meta
            tags.pop("distractor_regen_pending", None)
            action = f"{action}+new_dist"
        elif answer_corrected:
            tags["distractor_regen_pending"] = True
            dmeta = []
            action = f"{action}+regen_pending"

    return {
        "status": "success",
        "correct_answer": final_answer,
        "distractor_meta": dmeta,
        "tags": tags,
        "action": action,
        "verification_status": _verification_status(tags),
    }
