"""
Smart Verify pipeline — isolated compute (code_execution) + distractor generation.

Strict rule: answer verification and distractor generation are NEVER combined in one LLM call.
"""
from __future__ import annotations

import logging
import re
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
from src.pipeline.distractor_gate import effective_distractor_answer_type
from src.pipeline.deepseek_client import (
    call_deepseek_code_execution,
    call_deepseek_structured,
)
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


_PROSE_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]{3,}")
_INTEGRATION_CONSTANT_RE = re.compile(
    r"\+\s*(?:\\(?:mathrm|text)\s*\{\s*)?C\s*\}?"
    r"(?=$|[^A-Za-zА-Яа-яЁё])",
    re.I,
)
_CHOICE_STEM_RE = re.compile(
    r"\b(?:какое|какая|какой)\s+из\b",
    re.I,
)
_CHOICE_ITEM_RE = re.compile(
    r"(?:^|[\n;])\s*(?:[А-ЯA-Zа-яa-z]\)|\d+[.)])",
)
_PERCENT_WORD_RE = re.compile(r"\bпроцент\w*\b|%", re.I)


def _has_semantic_answer_prose(value: str | None) -> bool:
    """Whether an answer carries meaning that a bare computed value loses.

    Some historical rows are typed ``exact_number`` although the question asks
    to assess a student's claim (for example, ``Верно, интеграл равен 6``).
    Replacing such a response with just ``6`` changes the educational meaning.
    A mathematical engine may still supply a candidate, but the row must go to
    review unless a dedicated response-format route handles it.
    """
    text_value = re.sub(r"\$[^$]*\$", " ", str(value or ""))
    words = _PROSE_WORD_RE.findall(text_value)
    return len(words) >= 2


def _has_integration_constant(value: str | None) -> bool:
    """Recognise the arbitrary constant in an indefinite-integral answer."""
    text_value = str(value or "").replace("$", " ")
    return bool(_INTEGRATION_CONSTANT_RE.search(text_value))


def _has_percent_marker(value: str | None) -> bool:
    return "%" in str(value or "").replace(r"\%", "%")


def _question_requires_percent(question: str) -> bool:
    return bool(_PERCENT_WORD_RE.search(question or ""))


def _question_has_missing_choice_content(question: str) -> bool:
    """Detect a choice stem whose actual choices were lost during import.

    A sentence such as «Какое из уравнений не является биквадратным?» cannot
    be independently solved without the equations.  The answer label alone
    is not evidence and must never be rewritten by a model.
    """
    text_value = (question or "").strip()
    if not _CHOICE_STEM_RE.search(text_value):
        return False
    if _CHOICE_ITEM_RE.search(text_value):
        return False
    # At least two inline math fragments normally carry the alternatives when
    # they are not expressed as a labelled list.
    return len(re.findall(r"\$[^$]+\$", text_value)) < 2


def _requires_response_route(answer_type: str, stored_answer: str | None) -> bool:
    """Whether a historically numeric row actually expects a response-style answer.

    ``answer_type`` is source metadata and must never be rewritten by Smart
    Verify.  Some legacy imports, however, label answers such as ``да``, a
    pupil's name, or ``красная лента, 1/5 м`` as ``exact_number``.  Sending
    them to the code/SymPy route is a category error: a number-only gate
    cannot certify a semantically complete school answer.

    This is intentionally narrow.  It only re-routes source numeric types
    when the *stored answer* contains a meaningful Cyrillic word.  Bare
    values with units (``81 кв. м``) still use the mathematical route, so we
    do not turn ordinary numerical tasks into LLM-only checks.
    """
    declared = (answer_type or "").lower().strip()
    if declared not in {"exact_number", "decimal", "fraction"}:
        return False

    raw = str(stored_answer or "")
    # Mathematical fragments are presentation, not a semantic response.
    prose = re.sub(r"\$[^$]*\$", " ", raw)
    # A full verdict about someone else's answer is not a short response.  It
    # must stay on the strict mathematical route, whose existing guard keeps
    # the source sentence intact instead of treating the embedded number as a
    # replacement candidate.
    if re.search(
        r"(?:правильн\w*\s+ответ|неверн\w*|ошиб\w*|проверь\w*|"
        r"ни\s+при\s+каком|нет\s+(?:корн\w*|решен\w*))",
        prose,
        re.I,
    ):
        return False
    if prose.strip().casefold() in {"да", "нет", "верно", "неверно"}:
        return True
    words = [word.casefold() for word in _PROSE_WORD_RE.findall(prose)]
    if not words:
        return False

    # A sole unit abbreviation is not an answer format.  Full measurement
    # wording remains numeric as well; numerical equivalence preserves it.
    unit_words = {
        "метр", "метра", "метров", "сантиметр", "сантиметра",
        "сантиметров", "килограмм", "килограмма", "килограммов",
        "литр", "литра", "литров", "градус", "градуса", "градусов",
    }
    return any(word not in unit_words for word in words)


def _build_compute_prompt(
    task_id: str,
    question: str,
    answer_type: str,
    stored_answer: Optional[str],  # kept in signature for compat, but NOT used in prompt
    *,
    alt_method: bool = False,
    prior_gate_error: str = "",
) -> str:
    # ВАЖНО: stored_answer намеренно НЕ передаётся в промпт.
    # LLM должна решать задачу независимо, без "якорения" на ответ из учебника.
    # Сравнение с учебником происходит ПОСЛЕ независимого вычисления.
    alt_line = (
        "\nРеши задачу другим методом (другой подход, другое разложение и т.п.).\n"
        if alt_method else ""
    )
    retry_guard = ""
    if prior_gate_error == "invalid_boolean_result":
        retry_guard = (
            "\nПредыдущая попытка ошибочно вернула True/False вместо ответа. "
            "В этой попытке вычисли и верни сам ответ задачи — число, дробь, "
            "выражение, слово или пару значений; булево утверждение использовать нельзя.\n"
        )
    elif prior_gate_error in {"eval_failed", "undecidable_equivalence"}:
        retry_guard = (
            "\nПредыдущая попытка дала непроверяемую SymPy-строку. "
            "Построй простое исполнимое выражение, которое вычисляет именно "
            "требуемый ответ, а не только исходное условие или промежуточный объект.\n"
        )
    return (
        "Ты — точный математический решатель. Реши задачу с помощью Python/SymPy.\n"
        "НЕ рассуждай вслух. Напиши только Python-код с результатом.\n\n"
        f"ID задачи: {task_id}\n"
        f"Тип ответа: {answer_type}\n"
        f"Текст задачи:\n{question}\n\n"
        f"{alt_line}"
        f"{retry_guard}"
        "Код должен присвоить переменной `result` словарь с ключами:\n"
        "- sympy_compatible_string: SymPy-выражение (напр. Eq(2*x-4, 10) или solve(...))\n"
        "- absolute_correct_answer: финальный ответ в школьной записи (только значение)\n\n"
        "ВАЖНО: sympy_compatible_string обязан вычислять именно величину, "
        "которую спрашивает задача. Если требуется параметр a, при котором "
        "два уравнения имеют общий корень, сначала найди общий корень x, затем "
        "реши второе уравнение относительно a. Не подставляй готовый a в "
        "уравнение с x: такая строка проверяет x, а не запрошенный параметр.\n\n"
        "Никогда не возвращай проверку вида Eq(вычисленное, ожидаемое), True "
        "или False вместо ответа: строка должна вычисляться в сам финальный "
        "результат. Для задания на знак сравнения верни пару вычисленных "
        "значений как (левое, правое), а absolute_correct_answer — только знак "
        "<, >, =, <= или >=. Для ответа-разряда верни номер разряда "
        "(0=единицы, 1=десятки, 2=сотни, 3=тысячи и т.д.), а в "
        "absolute_correct_answer — название разряда.\n\n"
        "Для нескольких корней используй '; ' как разделитель.\n"
        "Верни ТОЛЬКО блок ```python ... ``` без пояснений."
    )


def _build_structured_compute_prompt(
    task_id: str,
    question: str,
    answer_type: str,
    *,
    prior_gate_error: str = "",
) -> str:
    """Prompt for the JSON fallback when generated Python is not executable.

    The fallback is deliberately not a permissive text answer.  It returns the
    same two independent pieces of evidence as the code route, and the caller
    always sends both through ``sympy_gate`` before any status can advance.
    """
    retry_context = (
        f"Предыдущая техническая проверка не прошла: {prior_gate_error}. "
        "Не повторяй эту ошибку. "
        if prior_gate_error else ""
    )
    return (
        "Ты — независимый точный математический решатель. Реши задачу с нуля; "
        "сохранённый ответ учебника тебе намеренно не показан.\n\n"
        f"ID задачи: {task_id}\n"
        f"Тип ответа: {answer_type}\n"
        f"Текст задачи:\n{question}\n\n"
        f"{retry_context}"
        "Верни JSON строго по схеме с полями `sympy_compatible_string` и "
        "`absolute_correct_answer`. `sympy_compatible_string` обязан быть "
        "простым исполнимым SymPy-выражением, которое вычисляет ИМЕННО "
        "запрошенный итоговый ответ. `absolute_correct_answer` — тот же итог "
        "в школьной записи. Не возвращай True/False, подстановку готового "
        "ответа, исходное уравнение без решения или промежуточные значения. "
        "Для нескольких корней используй разделитель '; '."
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
    prior_gate_error: str = "",
) -> tuple[Optional[SmartVerifyResponse], Optional[SympyGateResult], Optional[str]]:
    """One code_execution run + gate. Returns (llm_result, gate, canonical)."""
    prior_gate_error = str(prior_gate_error or "").split(":", 1)[0]
    # Retry a known serialization/execution failure through JSON directly.
    # Repeating a program that has already produced a boolean proof token or
    # an unparsable result wastes quota and is less reliable than a strict
    # schema response.  This is still an independent computation followed by
    # the same local mathematical gate.
    direct_structured = prior_gate_error in {
        "invalid_boolean_result",
        "eval_failed",
        "gemini_code_execution_failed",
        "empty_absolute_correct_answer",
    }
    llm_result: Optional[SmartVerifyResponse] = None
    if not direct_structured:
        try:
            llm_result = call_deepseek_code_execution(
                _build_compute_prompt(
                    task_id,
                    question,
                    atype,
                    stored,
                    alt_method=alt_method,
                    prior_gate_error=prior_gate_error,
                ),
                schema=SmartVerifyResponse,
                temperature=temperature,
                # A code-route failure is retried through the structured route
                # below.  One bounded attempt keeps a single slow request from
                # holding a worker for several minutes.
                timeout=45,
                max_retries=1,
            )
        except Exception as exc:
            log.warning("Smart verify code route failed %s: %s; trying JSON fallback", task_id, exc)

    if llm_result is not None:
        code_result = _gate_compute_response(llm_result, atype, stored, question)
        if code_result[1] is not None and code_result[1].ok:
            return code_result
        # A syntactically valid program can still return an unusable proof
        # token such as True, an unevaluated equation, or the wrong target
        # variable.  A second, schema-constrained formulation is justified
        # only for these failed local gates; it remains subject to the same
        # deterministic validation below.
        if code_result[1] is not None:
            prior_gate_error = code_result[1].reason or prior_gate_error
            # A locally computed mathematical disagreement is substantive
            # evidence, not a formatting failure to be papered over by a
            # second model call.  Keep it for protected human review.
            if prior_gate_error not in {
                "invalid_boolean_result",
                "eval_failed",
                "undecidable_equivalence",
            }:
                return code_result

    try:
        structured = call_deepseek_structured(
            _build_structured_compute_prompt(
                task_id,
                question,
                atype,
                prior_gate_error=prior_gate_error,
            ),
            schema=SmartVerifyResponse,
            temperature=temperature,
            timeout=45,
            max_retries=1,
        )
    except Exception as exc:
        log.warning("Smart verify JSON fallback failed %s: %s", task_id, exc)
        return None, None, None

    return _gate_compute_response(structured, atype, stored, question)


def _gate_compute_response(
    llm_result: SmartVerifyResponse,
    atype: str,
    stored: Optional[str],
    question: str,
    *,
    gate_timeout_seconds: Optional[int] = None,
) -> tuple[SmartVerifyResponse, Optional[SympyGateResult], Optional[str]]:
    """Run the local mathematical gate for a new or already-saved LLM result."""
    computed_answer = (llm_result.absolute_correct_answer or "").strip()
    if not computed_answer:
        return llm_result, None, None

    gate = sympy_gate(
        llm_result.sympy_compatible_string,
        computed_answer,
        atype,
        question=question,
        stored_answer=stored or "",
        timeout_seconds=gate_timeout_seconds,
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
    precomputed_response: Optional[SmartVerifyResponse] = None,
    precomputed_gate_timeout_seconds: Optional[int] = None,
    allow_distractor_generation: bool = True,
    require_unanimous_consensus: bool = False,
    allow_source_correction: bool = False,
) -> dict[str, Any]:
    """
    Smart Verify for one task (compute or text route).

    Returns dict with keys: status, correct_answer, distractor_meta, tags, action.
    """
    tags = dict(tags or {})
    dmeta = list(distractor_meta or [])
    source_atype = (answer_type or "exact_number").lower().strip()
    stored = (correct_answer or "").strip() or None
    if not (question or "").strip():
        sync_verify_tags(tags, "needs_content_repair")
        tags["content_repair_reason"] = "missing_question_text"
        tags.pop("answer_gemini_verified", None)
        tags.pop("answer_locked", None)
        return {
            "status": "skipped",
            "correct_answer": stored or "",
            "correct_answer_latex": to_answer_latex(stored or "", source_atype),
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "needs_content_repair_missing_question_text",
            "verification_status": "pending",
        }
    if _question_has_missing_choice_content(question):
        sync_verify_tags(tags, "needs_content_repair")
        tags["content_repair_reason"] = "choice_stem_without_choice_content"
        tags.pop("answer_gemini_verified", None)
        tags.pop("answer_locked", None)
        return {
            "status": "skipped",
            "correct_answer": stored or "",
            "correct_answer_latex": to_answer_latex(stored or "", source_atype),
            "distractor_meta": dmeta,
            "tags": tags,
            "action": "needs_content_repair_choice_stem_without_choice_content",
            "verification_status": "pending",
        }
    # Keep source metadata immutable, but route legacy records through the
    # answer domain their question and answer actually require.  This is the
    # same classifier used by the distractor validator, so answer verification
    # and choices cannot disagree about whether ``(3; 1)`` is a number,
    # coordinate pair, or solution set.
    atype = effective_distractor_answer_type(
        question or "", stored or "", source_atype,
    )
    if atype != source_atype:
        tags["smart_verify_effective_answer_type"] = atype
        tags["smart_verify_source_answer_type"] = source_atype
    else:
        tags.pop("smart_verify_effective_answer_type", None)
        tags.pop("smart_verify_source_answer_type", None)
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
            tags["choices_complete"] = True
            tags.pop("distractor_regen_pending", None)
            return {
                "status": "success",
                "correct_answer": stored or "",
                "correct_answer_latex": to_answer_latex(stored or "", atype),
                "distractor_meta": dmeta,
                "tags": tags,
                "action": "already_locked_skip",
                "verification_status": verification_status(tags),
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

    # Preserve the historical source type, but use the response-aware text
    # contract for legacy rows whose answer is not a number.  The text route
    # has an independent two-pass consensus check and a full distractor gate;
    # it is not a permissive bypass around verification.  It is deliberately
    # used instead of the narrower MCQ route because it can preserve a source
    # answer such as «Ворчун, 11/27 кг» when the independent solver says the
    # same thing in a longer sentence.
    is_response_route = _requires_response_route(source_atype, stored)
    # A semantic route has no mathematical proof oracle.  It is therefore
    # certified only by three independent answers, even during the ordinary
    # ``human`` recovery queue.  Computable answer types keep their existing
    # one-pass LLM + local SymPy gate unless an explicit arbitration asks for
    # three gated computations.
    semantic_consensus_required = (
        require_unanimous_consensus
        or is_response_route
        or atype in TEXT_VERIFY_TYPES
        or atype in {"coordinate", "multiple_choice"}
    )

    if is_response_route:
        result = run_text_verify_pipeline(
            task_id=task_id,
            question=question,
            correct_answer=correct_answer,
            answer_type="text",
            distractor_meta=dmeta,
            tags=tags,
            answer_authority=answer_authority,
            preserve_source_on_mismatch=not allow_source_correction,
            require_unanimous_consensus=semantic_consensus_required,
        )
        result_tags = dict(result.get("tags") or {})
        result_tags["smart_verify_effective_answer_type"] = "text"
        result_tags["smart_verify_source_answer_type"] = source_atype
        result["tags"] = result_tags
        return result

    if atype == "multiple_choice":
        return run_mcq_verify_pipeline(
            task_id=task_id,
            question=question,
            correct_answer=correct_answer,
            distractor_meta=dmeta,
            tags=tags,
            answer_authority=answer_authority,
            require_unanimous_consensus=semantic_consensus_required,
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
            # In textbook-authority mode an LLM result is evidence, never
            # permission to replace a source prose/coordinate answer.  A
            # disagreement stays pending with the candidate recorded for a
            # reviewer, exactly like legacy numeric rows routed as text.
            preserve_source_on_mismatch=(
                authority == "textbook" and not allow_source_correction
            ),
            require_unanimous_consensus=semantic_consensus_required,
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

    retry_attempt = int(tags.get("smart_verify_retry_count", 0) or 0)
    retry_settings = get_settings()
    arbitration_votes: list[str] | None = None
    if require_unanimous_consensus and precomputed_response is None:
        # Do not let a malformed first SymPy program silently reduce a
        # three-solver arbitration to one attempt. Every solver is called;
        # only locally gated final answers count as a vote.
        required_runs = max(3, retry_settings.smart_verify_consistency_runs)
        successful_attempts: list[
            tuple[SmartVerifyResponse, SympyGateResult, str]
        ] = []
        fallback_candidate = ""
        gate_reasons: list[str] = []
        for attempt in range(required_runs):
            attempt_result, attempt_gate, attempt_canonical = _run_single_compute(
                task_id,
                question,
                atype,
                stored,
                alt_method=attempt > 0,
                temperature=(
                    retry_settings.smart_verify_consistency_temperature
                    if attempt > 0 else 0.0
                ),
                prior_gate_error=str(
                    tags.get("smart_verify_error") or ""
                ).split(":", 1)[0],
            )
            if attempt_result and not fallback_candidate:
                fallback_candidate = (
                    attempt_result.absolute_correct_answer or ""
                ).strip()
            gate_reasons.append(
                attempt_gate.reason if attempt_gate is not None else "llm_unavailable"
            )
            if attempt_result and attempt_gate and attempt_gate.ok and attempt_canonical:
                successful_attempts.append(
                    (attempt_result, attempt_gate, attempt_canonical)
                )

        tags["smart_verify_consensus_required"] = required_runs
        tags["smart_verify_consensus_obtained"] = len(successful_attempts)
        tags["smart_verify_arbitration_gate_reasons"] = gate_reasons
        if len(successful_attempts) < required_runs:
            sync_verify_tags(tags, "needs_human_review")
            tags["smart_verify_consensus_unanimous"] = False
            tags["smart_verify_arbitration_reason"] = "incomplete_gated_consensus"
            tags["answer_gemini_candidate"] = fallback_candidate[:500]
            tags.pop("answer_gemini_verified", None)
            return {
                "status": "review",
                "correct_answer": stored or "",
                "correct_answer_latex": to_answer_latex(stored or "", atype),
                "distractor_meta": dmeta,
                "tags": tags,
                "action": "needs_human_review_incomplete_gated_consensus",
                "verification_status": "pending",
            }

        llm_result, gate, canonical = successful_attempts[0]
        arbitration_votes = [item[2] for item in successful_attempts]
    elif precomputed_response is not None:
        # A previous model response is evidence, never an automatic pass: it
        # still goes through the current local gate.  This lets us safely
        # recover rows blocked only by an older parser without spending a
        # second model call or changing the original task text.
        llm_result, gate, canonical = _gate_compute_response(
            precomputed_response,
            atype,
            stored,
            question,
            gate_timeout_seconds=precomputed_gate_timeout_seconds,
        )
    else:
        llm_result, gate, canonical = _run_single_compute(
            task_id,
            question,
            atype,
            stored,
            alt_method=retry_attempt > 0,
            temperature=(
                retry_settings.smart_verify_consistency_temperature
                if retry_attempt > 0 else 0.0
            ),
            prior_gate_error=str(tags.get("smart_verify_error") or "").split(":", 1)[0],
        )
    if llm_result is None:
        return _error_result(
            tags=tags, status_key="failed_at_llm", action="failed_at_llm",
            stored=stored, dmeta=dmeta, error="gemini_code_execution_failed",
        )

    # A replay only re-evaluates an already stored model response.  It must
    # preserve the genuine LLM-attempt budget while still clearing obsolete
    # failure flags once the strengthened local gate proves the answer.
    if precomputed_response is not None:
        tags.pop("smart_verify_retry_count", None)
        tags.pop("smart_verify_retry_exhausted", None)
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
    # Smart Verify stores only evidence needed to verify the final answer.
    # A prose solution is intentionally not requested or persisted: distractors
    # are generated independently from the task and the verified answer.
    tags.pop("step_by_step_solution", None)

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
    ) and not require_unanimous_consensus:
        sync_verify_tags(tags, "verified_match")
        final_answer = stored
        need_distractors = not has_old_distractors
        tags["answer_format_preserved"] = True
    else:
        if authority == "textbook" and not allow_source_correction:
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
        votes = list(arbitration_votes or [final_answer])
        n_runs = max(
            3 if require_unanimous_consensus else 1,
            settings.smart_verify_consistency_runs,
        )
        if arbitration_votes is None:
            for _ in range(n_runs - 1):
                _llm2, gate2, canon2 = _run_single_compute(
                    task_id, question, atype, stored,
                    alt_method=True,
                    temperature=settings.smart_verify_consistency_temperature,
                    prior_gate_error=str(tags.get("smart_verify_error") or "").split(":", 1)[0],
                )
                if gate2 and gate2.ok and canon2:
                    votes.append(canon2)

        tags["self_consistency_votes"] = votes[:10]
        winner, unanimous, _all = pick_consensus_canonical(votes, atype)
        if require_unanimous_consensus:
            tags["smart_verify_consensus_required"] = n_runs
            tags["smart_verify_consensus_obtained"] = len(votes)
            tags["smart_verify_consensus_unanimous"] = bool(
                len(votes) >= n_runs and unanimous
            )
            # Three independently generated, locally gated answers are the
            # minimum evidence for a corrective source write. A 2:1 majority
            # or an unavailable run remains reviewable, never auto-corrected.
            if len(votes) < n_runs or not unanimous:
                sync_verify_tags(tags, "needs_human_review")
                tags["smart_verify_arbitration_reason"] = "non_unanimous_consensus"
                tags["answer_gemini_candidate"] = final_answer[:500]
                tags.pop("answer_gemini_verified", None)
                return {
                    "status": "review",
                    "correct_answer": stored,
                    "correct_answer_latex": to_answer_latex(stored or "", atype),
                    "distractor_meta": dmeta,
                    "tags": tags,
                    "action": "needs_human_review_non_unanimous_consensus",
                    "verification_status": "pending",
                }
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

        if _question_requires_percent(question) and not _has_percent_marker(winner):
            # The model may compute a ratio but omit the required conversion
            # to percent and/or the requested rounding.  This is not a valid
            # candidate for a source rewrite.
            sync_verify_tags(tags, "needs_human_review")
            tags["smart_verify_arbitration_reason"] = "required_percent_format_missing"
            tags["answer_gemini_candidate"] = winner[:500]
            tags.pop("answer_gemini_verified", None)
            return {
                "status": "review",
                "correct_answer": stored,
                "correct_answer_latex": to_answer_latex(stored or "", atype),
                "distractor_meta": dmeta,
                "tags": tags,
                "action": "needs_human_review_required_percent_format_missing",
                "verification_status": "pending",
            }
        if (
            _has_integration_constant(stored)
            and not _has_integration_constant(winner)
        ):
            # A source answer containing ``+ C`` is more complete than a
            # candidate that merely gives one antiderivative.  SymPy can prove
            # their derivatives equal, but must never use that to erase the
            # arbitrary constant from the student-facing answer.
            sync_verify_tags(tags, "verified_match")
            final_answer = stored
            need_distractors = not has_old_distractors
            tags["answer_format_preserved"] = True
            tags["smart_verify_arbitration_format_guard"] = "preserved_integration_constant"
        elif stored_answer_matches_compute(stored, winner, answer_type=atype):
            sync_verify_tags(tags, "verified_match")
            final_answer = stored
            need_distractors = not has_old_distractors
            tags["answer_format_preserved"] = True
        else:
            if _has_semantic_answer_prose(stored):
                # The numeric/algebraic candidate is evidence, not a safe
                # replacement for a prose verdict.  Preserve the source until
                # a response-aware review can construct the full answer.  This
                # remains true in an arbitration: three model outputs can
                # agree on a bare number while omitting the source verdict.
                sync_verify_tags(tags, "needs_human_review")
                tags["answer_format_review_required"] = True
                tags["answer_gemini_candidate"] = winner[:500]
                tags.pop("answer_gemini_verified", None)
                return {
                    "status": "review",
                    "correct_answer": stored,
                    "correct_answer_latex": to_answer_latex(stored or "", atype),
                    "distractor_meta": dmeta,
                    "tags": tags,
                    "action": "needs_human_review_answer_format",
                    "verification_status": "pending",
                }
            tags["answer_previous"] = stored
            # Any explanation written for the previous answer is stale after a
            # verified correction and must never leak into reports.
            tags.pop("verification_explanation", None)
            tags.pop("answer_verification_explanation", None)
            final_answer = winner
            sync_verify_tags(tags, "verified_corrected")
            if not unanimous:
                tags["self_consistency_majority"] = True
            dmeta = []
            need_distractors = True
            answer_corrected = True

    if tags.get("smart_verify_status") not in ("needs_human_review",):
        clear_stale_verify_flags(tags)
        if require_unanimous_consensus:
            # ``self_consistency_votes`` is transient retry evidence and is
            # normally cleared on success. An arbitration correction needs a
            # durable audit trail proving which three gated answers agreed.
            tags["smart_verify_arbitration_votes"] = votes[:10]
        tags["answer_gemini_verified"] = True
        tags["answer_locked"] = True
        tags["sympy_gate_reason"] = gate.reason
        tags["answer_source"] = (
            "computed" if answer_corrected and has_old_answer
            else "textbook" if has_old_answer else "computed"
        )

    action = tags.get("smart_verify_status", "unknown")
    if need_distractors and not allow_distractor_generation:
        # Replay proves only the saved answer evidence.  Distractor generation
        # is a separate model operation and must stay in its own queue so this
        # local pass can never spend model quota or hide an incomplete task.
        tags["choices_complete"] = False
        tags["distractor_regen_pending"] = True
        action = f"{action}+regen_deferred"
    else:
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
