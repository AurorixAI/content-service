"""LLM pedagogy audit for stored distractor error_logic (values unchanged)."""
from __future__ import annotations

import logging
from typing import Any

from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model, parse_json_response
from src.schemas.smart_verify import PedagogyItemReview, PedagogyReviewResponse

_PEDAGOGY_JSON_HINT = (
    '{"items":[{"index":0,"status":"ok|rewrite|reject_value",'
    '"error_logic":"...","issue":"..."}],"overall":"pass|needs_regen"}'
)

log = logging.getLogger(__name__)

_GENERIC_MARKERS = (
    "ученик ошибся",
    "ошибка при вычислении",
    "неправильно решил",
    "типичная ошибка",
    "ошибка в задаче",
    "не знает ответ",
)


def distractor_logic_text(item: dict) -> str:
    return str(item.get("error_logic") or item.get("explanation") or "").strip()


def _build_prompt(
    *,
    question: str,
    correct_answer: str,
    answer_type: str,
    distractors: list[dict],
) -> str:
    lines = []
    for i, d in enumerate(distractors):
        lines.append(
            f"{i}. value={d.get('value', '')!r}\n"
            f"   error_logic={distractor_logic_text(d)!r}"
        )
    dist_block = "\n".join(lines)
    return (
        "Ты — опытный учитель математики. Проверь педагогическое качество error_logic "
        "у дистракторов (НЕ меняй value).\n\n"
        f"Вопрос: {question}\n"
        f"Правильный ответ: {correct_answer}\n"
        f"Тип ответа: {answer_type}\n\n"
        f"Дистракторы:\n{dist_block}\n\n"
        "Критерии для каждого дистрактора:\n"
        "- ok: конкретная реалистичная школьная ошибка, объясняет ИМЕННО это value\n"
        "- rewrite: value норм, но error_logic слишком общий/натянутый/короткий — "
        "перепиши error_logic (мин. 25 символов, конкретный шаг)\n"
        "- reject_value: value неправдоподобен как ошибка ИЛИ логика не может "
        "привести к этому value — нужна полная перегенерация dist\n\n"
        "overall=pass если все ok или rewrite (без reject_value).\n"
        "overall=needs_regen если хотя бы один reject_value.\n"
        f"Верни JSON: {_PEDAGOGY_JSON_HINT}\n"
    )


def _parse_pedagogy_response(raw: object) -> PedagogyReviewResponse:
    if not isinstance(raw, dict):
        raise ValueError("pedagogy response must be a JSON object")
    return PedagogyReviewResponse.model_validate(raw)


def audit_distractor_pedagogy(
    *,
    question: str,
    correct_answer: str,
    answer_type: str,
    distractors: list[dict],
) -> PedagogyReviewResponse:
    if not distractors:
        return PedagogyReviewResponse(items=[], overall="needs_regen")
    prompt = _build_prompt(
        question=question,
        correct_answer=correct_answer,
        answer_type=answer_type,
        distractors=distractors,
    )
    text = call_deepseek(
        prompt,
        model=get_deepseek_model(),
        temperature=0.1,
        max_tokens=2048,
    )
    return _parse_pedagogy_response(parse_json_response(text))


def apply_pedagogy_review(
    distractors: list[dict],
    review: PedagogyReviewResponse,
) -> tuple[list[dict], str]:
    """
    Apply LLM pedagogy review to distractor_meta copy.
    Returns (updated_meta, outcome) where outcome is pass | needs_regen | invalid_review.
    """
    if not distractors:
        return [], "needs_regen"

    by_index: dict[int, PedagogyItemReview] = {}
    for item in review.items:
        if item.index not in by_index:
            by_index[item.index] = item

    updated: list[dict] = []
    needs_regen = False
    for i, d in enumerate(distractors):
        if not isinstance(d, dict):
            continue
        out = dict(d)
        rev = by_index.get(i)
        if rev is None:
            return list(distractors), "invalid_review"

        status = (rev.status or "").strip().lower()
        if status == "reject_value":
            needs_regen = True
            continue
        if status == "rewrite":
            text = (rev.error_logic or "").strip()
            if len(text) < 15:
                needs_regen = True
                continue
            out["error_logic"] = text
            out["explanation"] = text
        elif status != "ok":
            return list(distractors), "invalid_review"
        updated.append(out)

    if needs_regen or review.overall.strip().lower() == "needs_regen":
        return list(distractors), "needs_regen"
    if len(updated) < 2:
        return list(distractors), "needs_regen"
    return updated, "pass"


def looks_generic_error_logic(text: str) -> bool:
    """Fast pre-filter before LLM — obvious weak templates."""
    el = (text or "").strip().lower()
    if len(el) < 20:
        return True
    return any(m in el for m in _GENERIC_MARKERS) and len(el) < 45
