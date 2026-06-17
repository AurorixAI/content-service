"""Content Service — Distractor Generation

All answer types → Gemini generates context-aware student mistakes.
For exact_number/decimal: SymPy validates distractor ≠ correct answer.
Smart Verify calls generate_distractors(verify_answer=False) — isolated teacher step.
"""
from __future__ import annotations

import logging

from src.pipeline.models import ExtractedTask

log = logging.getLogger(__name__)

_NUMERIC_TYPES = {"exact_number", "decimal"}


def _has_distractors(task: ExtractedTask) -> bool:
    meta = task.distractor_meta
    return isinstance(meta, list) and len(meta) > 0


def _clear_distractors(task: ExtractedTask) -> None:
    task.distractor_meta = []
    task.distractors = []


def _solution_block(task: ExtractedTask) -> str:
    sol = (task.tags or {}).get("step_by_step_solution", "")
    if sol:
        return f"Пошаговое решение:\n{sol}\n\n"
    return ""


def _filter_distractor_collisions(
    items: list[dict],
    correct_answer: str,
    answer_type: str,
    *,
    max_count: int = 3,
) -> list[dict]:
    """Drop distractors equivalent to the correct answer (all types)."""
    from src.pipeline.answer_verify import answers_equivalent

    validated: list[dict] = []
    seen: set[str] = set()
    correct_norm = (correct_answer or "").strip().lower()

    for d in items:
        val = str(d.get("value", d.get("error_logic", ""))).strip()
        if not val:
            continue
        if val.lower() in seen:
            continue
        if val.lower() == correct_norm:
            continue
        if answers_equivalent(val, correct_answer, answer_type):
            continue
        validated.append(d)
        seen.add(val.lower())
        if len(validated) >= max_count:
            break
    return validated


def generate_distractors(
    task: ExtractedTask,
    *,
    verify_answer: bool = True,
    force_distractors: bool = False,
) -> ExtractedTask:
    """Generate distractors; optionally run legacy verify first.

    Smart Verify passes verify_answer=False, force_distractors=True.
    """
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
            log.info(
                "Distractors skipped (%s): %s",
                task.temp_id,
                vr.skip_reason,
            )
            return task
        answer = (task.answer_raw or "").strip()
        if not answer:
            return task

        if not answer_corrected and _has_distractors(task) and not force_distractors:
            log.debug("Distractors kept (verified answer): %s", task.temp_id)
            return task

    elif not force_distractors and _has_distractors(task):
        log.debug("Distractors kept (no regen requested): %s", task.temp_id)
        return task

    if answer_corrected or (not verify_answer and force_distractors and not _has_distractors(task)):
        if verify_answer and answer_corrected:
            _clear_distractors(task)
            if not task.tags:
                task.tags = {}
            task.tags["distractors_cleared_for_correction"] = True

    atype = (task.answer_type or "exact_number").lower().strip()

    try:
        if atype in _NUMERIC_TYPES:
            _ai_numeric(task, answer)
        else:
            _ai_text(task, answer)
    except Exception as exc:
        log.warning("Distractor generation failed (%s): %s", task.temp_id, exc)

    if (answer_corrected or (force_distractors and not _has_distractors(task))) and not _has_distractors(task):
        if not task.tags:
            task.tags = {}
        task.tags["distractor_regen_pending"] = True
        _clear_distractors(task)

    return task


def _ai_numeric(task: ExtractedTask, answer: str) -> None:
    try:
        from src.pipeline.gemini_client import call_gemini, get_pro_model, parse_json_response
        import sympy

        correct_val = float(answer.replace(",", "."))
        sol = _solution_block(task)

        prompt = (
            "Ты — опытный учитель математики. "
            "Придумай ровно 3 правдоподобных НЕВЕРНЫХ числовых ответа — типичные ошибки ученика.\n\n"
            f"Задача: {task.question_text}\n"
            f"{sol}"
            f"Правильный ответ: {answer}\n\n"
            "Требования:\n"
            "- Каждый дистрактор — конкретное число\n"
            "- Ни один не равен правильному ответу\n"
            "- Опиши конкретную ошибку ученика\n\n"
            'Верни JSON: [{"value":"число","explanation":"ошибка","error_logic":"ошибка"}]'
        )
        text = call_gemini(prompt, model=get_pro_model(), temperature=0.3, max_tokens=1024)
        items = parse_json_response(text)

        if not isinstance(items, list) or not items:
            raise ValueError("empty or invalid Gemini response")

        validated = []
        seen_vals: set = {correct_val}
        for d in items[:8]:
            val_str = str(d.get("value", "")).strip().replace(",", ".")
            try:
                d_val = float(val_str)
                diff = sympy.Abs(sympy.Rational(str(d_val)) - sympy.Rational(str(correct_val)))
                if float(diff) > 0 and d_val not in seen_vals:
                    validated.append(d)
                    seen_vals.add(d_val)
            except Exception:
                pass
            if len(validated) >= 3:
                break

        validated = _filter_distractor_collisions(
            validated, answer, task.answer_type or "exact_number", max_count=3,
        )
        if not validated:
            raise ValueError("no valid distractors after validation")

        task.distractors = [d.get("value", "") for d in validated]
        task.distractor_meta = [
            {
                "value": d.get("value", ""),
                "error_type": "ai_numeric",
                "explanation": d.get("explanation", d.get("error_logic", "")),
                "error_logic": d.get("error_logic", d.get("explanation", "")),
                "plausibility": 0.75,
            }
            for d in validated
        ]

    except Exception as exc:
        log.warning(
            "Gemini numeric distractor failed (%s): %s",
            task.temp_id,
            exc,
        )


def _ai_text(task: ExtractedTask, answer: str) -> None:
    try:
        from src.pipeline.gemini_client import call_gemini, get_pro_model, parse_json_response

        sol = _solution_block(task)
        prompt = (
            "Ты — математический педагог. Создай 3 правдоподобных НЕВЕРНЫХ ответа.\n\n"
            f"Вопрос: {task.question_text}\n"
            f"{sol}"
            f"Правильный ответ: {answer}\n\n"
            "Дистракторы НЕ должны совпадать с правильным ответом.\n"
            'Верни JSON: [{"value":"...","explanation":"...","error_logic":"..."}]\n'
            "Только JSON."
        )
        text = call_gemini(prompt, model=get_pro_model(), temperature=0.3, max_tokens=8192)
        items = parse_json_response(text)
        if not isinstance(items, list) or not items:
            raise ValueError("empty distractor list")

        filtered = _filter_distractor_collisions(
            items, answer, task.answer_type or "text", max_count=3,
        )
        if not filtered:
            raise ValueError("all distractors collided with correct answer")

        task.distractors = [d.get("value", "") for d in filtered]
        task.distractor_meta = [
            {
                "value": d.get("value", ""),
                "error_type": "ai_generated",
                "explanation": d.get("explanation", d.get("error_logic", "")),
                "error_logic": d.get("error_logic", d.get("explanation", "")),
                "plausibility": 0.75,
            }
            for d in filtered
        ]
    except Exception as exc:
        log.warning(
            "Gemini distractor failed (%s): %s",
            task.temp_id,
            exc,
        )
