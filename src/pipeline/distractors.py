"""Content Service — Distractor Generation

All answer types → Gemini generates context-aware student mistakes.
Smart Verify calls generate_distractors(verify_answer=False) — isolated teacher step.
Post-generation: distractor_gate L1–L4 validation with retry.
"""
from __future__ import annotations

import logging

from src.core.config import get_settings
from src.pipeline.distractor_gate import validate_distractor_set
from src.pipeline.models import ExtractedTask

log = logging.getLogger(__name__)

_NUMERIC_TYPES = {"exact_number", "decimal"}
_TEXT_TYPES = {"text", "open_text", "coordinate"}


def _required_distractor_count() -> int:
    """Target distractor count (ideal)."""
    return get_settings().distractor_gate_min_count


def _minimum_distractor_count() -> int:
    """Minimum acceptable: 1 correct + this many wrong (default 2 → 3 choices total)."""
    return get_settings().distractor_gate_min_acceptable


def _has_distractors(task: ExtractedTask) -> bool:
    meta = task.distractor_meta
    return isinstance(meta, list) and len(meta) > 0


def _has_complete_distractors(task: ExtractedTask) -> bool:
    meta = task.distractor_meta
    need = _minimum_distractor_count()
    return isinstance(meta, list) and len(meta) >= need


def _clear_distractors(task: ExtractedTask) -> None:
    task.distractor_meta = []
    task.distractors = []


def _solution_block(task: ExtractedTask) -> str:
    sol = (task.tags or {}).get("step_by_step_solution", "")
    if sol:
        return f"Пошаговое решение:\n{sol}\n\n"
    return ""


def _build_distractor_prompt(
    task: ExtractedTask,
    answer: str,
    *,
    rejected: list[dict] | None = None,
) -> str:
    atype = (task.answer_type or "exact_number").lower()
    sol = _solution_block(task)
    reject_block = ""
    if rejected:
        lines = [
            f"- {r.get('value', '?')}: {r.get('gate_reason', 'invalid')}"
            for r in rejected[:8]
        ]
        reject_block = (
            "\nРанее отклонённые варианты (не повторяй):\n"
            + "\n".join(lines)
            + "\n"
        )

    numeric_hint = ""
    if atype in _NUMERIC_TYPES:
        numeric_hint = "- Каждый дистрактор — конкретное число\n"

    type_hint = ""
    if atype in _TEXT_TYPES:
        type_hint = (
            "- Тип text: каждый дистрактор — другое неверное обоснование "
            "(разный шаг/ошибка), не перефраз одной и той же фразы\n"
            "- Если ответ да/нет или доказано/не доказано: варианты должны опираться "
            "на разные математические заблуждения\n"
        )
    elif atype == "inequality":
        type_hint = (
            "- Тип inequality: ядро — другое неверное неравенство (другой знак, граница "
            "или переменная), а не то же неравенство с иным «потому что»\n"
        )

    settings = get_settings()
    min_count = settings.distractor_gate_min_count
    batch_size = max(min_count, settings.distractor_gate_llm_batch_size)

    return (
        "Ты — опытный учитель математики. "
        f"Придумай ровно {batch_size} правдоподобных НЕВЕРНЫХ ответа — типичные ошибки ученика.\n\n"
        f"Задача: {task.question_text}\n"
        f"{sol}"
        f"Правильный ответ: {answer}\n"
        f"{reject_block}\n"
        "Требования:\n"
        f"{numeric_hint}"
        f"{type_hint}"
        "- Каждый дистрактор математически НЕВЕРЕН для этой задачи\n"
        "- Ошибка должна быть реалистичной (типичная ошибка на шаге решения)\n"
        "- error_logic: на каком шаге и как ошибся ученик (минимум 10 символов)\n"
        "- Ни один дистрактор не равен правильному ответу\n"
        "- Дистракторы должны отличаться друг от друга\n"
    )


def _items_to_meta(items: list[dict], error_type: str) -> tuple[list[str], list[dict]]:
    distractors = [str(d.get("value", "")) for d in items]
    meta = [
        {
            "value": d.get("value", ""),
            "error_type": error_type,
            "explanation": d.get("explanation", d.get("error_logic", "")),
            "error_logic": d.get("error_logic", d.get("explanation", "")),
            "plausibility": 0.75,
        }
        for d in items
    ]
    return distractors, meta


def _top_up_distractors(
    task: ExtractedTask,
    answer: str,
    accepted: list[dict],
    all_rejected: list[dict],
) -> list[dict]:
    """One focused LLM call to fill missing distractors (need exactly 3 total)."""
    from src.pipeline.gemini_client import call_gemini, get_pro_model, parse_json_response

    need = _required_distractor_count() - len(accepted)
    if need <= 0:
        return accepted

    atype = (task.answer_type or "exact_number").lower()
    skip_l3 = atype in _TEXT_TYPES
    min_count = _required_distractor_count()
    existing = [str(d.get("value", "")) for d in accepted]
    reject_lines = [
        f"- {r.get('value', '?')}: {r.get('gate_reason', 'invalid')}"
        for r in all_rejected[:10]
    ]
    prompt = (
        f"Задача: {task.question_text}\n"
        f"Правильный ответ: {answer}\n"
        f"Уже есть дистракторы (не повторяй): {existing}\n"
        + ("\nОтклонённые:\n" + "\n".join(reject_lines) + "\n" if reject_lines else "")
        + f"\nПридумай ещё ровно {need} НЕВЕРНЫХ ответа — типичные ошибки ученика.\n"
        "error_logic: минимум 10 символов, на каком шаге ошибся ученик.\n"
        f'Верни JSON: {{"distractors":[{{"value":"...","error_logic":"..."}}]}}\n'
    )
    try:
        text = call_gemini(prompt, model=get_pro_model(), temperature=0.4, max_tokens=1024)
        parsed = parse_json_response(text)
        if isinstance(parsed, dict) and "distractors" in parsed:
            items = parsed["distractors"]
        elif isinstance(parsed, list):
            items = parsed
        else:
            return accepted
        raw_items = [
            {
                "value": d.get("value", ""),
                "error_logic": d.get("error_logic", d.get("explanation", "")),
                "explanation": d.get("error_logic", d.get("explanation", "")),
            }
            for d in items
            if isinstance(d, dict)
        ]
        batch_accepted, batch_rejected = validate_distractor_set(
            raw_items,
            question=task.question_text or "",
            correct_answer=answer,
            answer_type=atype,
            max_count=need,
            skip_l3=skip_l3,
        )
        all_rejected.extend(batch_rejected)
        from src.pipeline.answer_verify import answers_equivalent

        for d in batch_accepted:
            val = str(d.get("value", "")).strip()
            if any(answers_equivalent(val, s, atype) for s in existing):
                continue
            if any(answers_equivalent(val, str(x.get("value", "")), atype) for x in accepted):
                continue
            accepted.append(d)
            existing.append(val)
            if len(accepted) >= min_count:
                break
    except Exception as exc:
        log.warning("Distractor top-up failed (%s): %s", task.temp_id, exc)
    return accepted


def _ai_generate_distractors(task: ExtractedTask, answer: str) -> None:
    from src.pipeline.gemini_client import get_pro_model

    settings = get_settings()
    atype = (task.answer_type or "exact_number").lower()
    skip_l3 = atype in _TEXT_TYPES or atype in ("inequality", "set")
    target = settings.distractor_gate_min_count
    minimum = settings.distractor_gate_min_acceptable
    max_retries = settings.distractor_gate_max_retries

    all_rejected: list[dict] = []
    accepted: list[dict] = []

    for attempt in range(max_retries + 1):
        prompt = _build_distractor_prompt(task, answer, rejected=all_rejected or None)
        from src.pipeline.gemini_client import call_gemini, parse_json_response

        try:
            text = call_gemini(
                prompt + '\nВерни JSON: {"distractors":[{"value":"...","error_logic":"..."}]}\n',
                model=get_pro_model(),
                temperature=0.3,
                max_tokens=2048,
            )
            parsed = parse_json_response(text)
            if isinstance(parsed, dict) and "distractors" in parsed:
                items = parsed["distractors"]
            elif isinstance(parsed, list):
                items = parsed
            else:
                raise ValueError("invalid distractor JSON")
            raw_items = [
                {
                    "value": d.get("value", ""),
                    "error_logic": d.get("error_logic", d.get("explanation", "")),
                    "explanation": d.get("error_logic", d.get("explanation", "")),
                }
                for d in items
                if isinstance(d, dict)
            ]
        except Exception as exc:
            log.warning("Distractor LLM failed (%s) attempt %d: %s", task.temp_id, attempt, exc)
            continue

        batch_accepted, batch_rejected = validate_distractor_set(
            raw_items,
            question=task.question_text or "",
            correct_answer=answer,
            answer_type=atype,
            max_count=target,
            skip_l3=skip_l3,
        )
        accepted.extend(batch_accepted)
        all_rejected.extend(batch_rejected)

        # Deduplicate accepted across retries
        unique: list[dict] = []
        seen_vals: list[str] = []
        for d in accepted:
            val = str(d.get("value", "")).strip()
            from src.pipeline.answer_verify import answers_equivalent
            if any(answers_equivalent(val, s, atype) for s in seen_vals):
                continue
            unique.append(d)
            seen_vals.append(val)
            if len(unique) >= target:
                break
        accepted = unique

        if len(accepted) >= target:
            break

    while len(accepted) < target:
        before = len(accepted)
        accepted = _top_up_distractors(task, answer, accepted, all_rejected)
        if len(accepted) >= target or len(accepted) == before:
            break

    if not task.tags:
        task.tags = {}
    task.tags["distractor_gate_passed"] = len(accepted)
    if all_rejected:
        task.tags["distractor_gate_rejected"] = [
            {"value": r.get("value"), "reason": r.get("gate_reason")}
            for r in all_rejected[:12]
        ]

    if len(accepted) < minimum:
        raise ValueError(
            f"only {len(accepted)} distractors passed gate (need at least {minimum})"
        )

    take = min(len(accepted), target)
    error_type = "ai_numeric" if atype in _NUMERIC_TYPES else "ai_generated"
    task.distractors, task.distractor_meta = _items_to_meta(accepted[:take], error_type)
    if not task.tags:
        task.tags = {}
    tags_n = len(task.distractor_meta or [])
    task.tags["choices_complete"] = tags_n >= minimum
    if tags_n < target:
        task.tags["distractor_count_partial"] = tags_n


def generate_distractors(
    task: ExtractedTask,
    *,
    verify_answer: bool = True,
    force_distractors: bool = False,
) -> ExtractedTask:
    """Generate distractors; optionally run legacy verify first."""
    answer = (task.answer_raw or "").strip()
    if not answer or answer == "\u2014":
        return task

    answer_corrected = False
    if verify_answer:
        from src.pipeline.answer_verify import apply_verify_to_task, verify_answer as _verify

        vr = _verify(
            task.question_text or "",
            answer,
            task.answer_type or "exact_number",
        )
        apply_verify_to_task(task, vr)
        answer_corrected = vr.corrected
        if vr.skip_distractors:
            log.info("Distractors skipped (%s): %s", task.temp_id, vr.skip_reason)
            return task
        answer = (task.answer_raw or "").strip()
        if not answer:
            return task

        if not answer_corrected and _has_complete_distractors(task) and not force_distractors:
            log.debug("Distractors kept (verified answer): %s", task.temp_id)
            return task

    elif not force_distractors and _has_complete_distractors(task):
        log.debug("Distractors kept (no regen requested): %s", task.temp_id)
        return task

    if answer_corrected or (not verify_answer and force_distractors and not _has_complete_distractors(task)):
        if verify_answer and answer_corrected:
            _clear_distractors(task)
            if not task.tags:
                task.tags = {}
            task.tags["distractors_cleared_for_correction"] = True

    try:
        _ai_generate_distractors(task, answer)
    except Exception as exc:
        log.warning("Distractor generation failed (%s): %s", task.temp_id, exc)

    need_complete = answer_corrected or (
        not verify_answer and force_distractors and not _has_complete_distractors(task)
    )
    if need_complete and not _has_complete_distractors(task):
        if not task.tags:
            task.tags = {}
        task.tags["distractor_regen_pending"] = True
        _clear_distractors(task)

    return task
