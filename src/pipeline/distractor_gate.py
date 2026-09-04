"""Distractor validation gate — L1 parseable, L2 collision, L3 not-a-solution, L4 plausible."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from src.pipeline.answer_sympy import parse_expr, try_validate_answer_for_question
from src.pipeline.answer_sympy_gate import _try_validate_equation_answer
from src.pipeline.answer_verify import (
    _norm,
    _normalize_ineq_symbols,
    _split_compound_parts,
)
from src.pipeline.distractor_collision import (
    _looks_numeric_school_answer,
    values_collide_for_distractor,
)

log = logging.getLogger(__name__)

_GARBAGE_RE = re.compile(
    r"^(не\s*знаю|неизвестно|\?+|—+|-+|n/?a)$",
    re.I,
)

_NUMERIC_TYPES = frozenset({"exact_number", "decimal", "fraction"})
_COMPUTABLE_TYPES = frozenset({
    "exact_number", "decimal", "fraction", "expression",
    "equation_solution", "inequality", "set", "multiple_choice",
})

_LABELED_PREFIX_RE = re.compile(r"^[а-г]\)\s*|^\d+\)\s*", re.I)
_INEQ_RE = re.compile(r"(?:<=|>=|≤|≥|!=|≠|<|>)")
_TRAILING_REASON_RE = re.compile(
    r",\s*(?:так как|потому что|так что|поскольку|значит|т\.?\s*к\.?).*$",
    re.I,
)
_NUMERIC_TEXT_RE = re.compile(
    r"^[\d\s.,+\-]+(?:/\d+)?(?:\s+\d+/\d+)?$",
)
_MIXED_FRAC_RE = re.compile(r"^\d+\s+\d+/\d+$")
_FRAC_RE = re.compile(r"^\d+/\d+$")


def _strip_trailing_reasoning(val: str) -> str:
    s = (val or "").strip()
    return _TRAILING_REASON_RE.sub("", s).strip()


def _extract_relation_core(val: str) -> Optional[str]:
    """Leading numeric inequality before optional «, потому что …» prose."""
    s = _normalize_ineq_symbols(_strip_trailing_reasoning(val))
    m = re.match(
        r"^([+-]?[\d.,/()\s]+)\s*(<=|>=|<|>|!=|≠)\s*([+-]?[\d.,/()\s]+)",
        s,
    )
    if not m:
        return None
    return f"{m.group(1).strip()} {m.group(2)} {m.group(3).strip()}"


def _looks_multipart(value: str) -> bool:
    val = (value or "").strip()
    if ";" in val:
        return True
    return bool(_LABELED_PREFIX_RE.search(val))


def _is_parseable_single(value: str, answer_type: str) -> bool:
    val = (value or "").strip()
    if not val or _GARBAGE_RE.match(val):
        return False

    at = (answer_type or "").lower()
    if at in ("text", "open_text"):
        # Compound text answers may contain single-digit numeric parts (e.g. "1; 3; 2.25").
        return len(val) >= 1

    if at in _NUMERIC_TYPES:
        try:
            float(val.replace(",", ".").replace(" ", ""))
            return True
        except ValueError:
            return parse_expr(val) is not None

    if at == "equation_solution":
        if re.search(r"=\s*", val):
            return True
        return parse_expr(val) is not None or bool(re.search(r"-?\d", val))

    if at in ("expression", "fraction", "inequality", "set"):
        if re.fullmatch(r"-?\d+(?:[.,]\d+)?", val.replace(" ", "")):
            return True
        if "/" in val:
            return True
        return parse_expr(val) is not None or len(val) >= 2

    return len(val) >= 2


def _is_parseable(value: str, answer_type: str) -> bool:
    val = (value or "").strip()
    if not val:
        return False
    at = (answer_type or "").lower()
    if _looks_multipart(val):
        parts = _split_compound_parts(val)
        if len(parts) >= 2:
            return all(_is_parseable_single(p, at) for p in parts)
    return _is_parseable_single(val, at)


def _is_implausible(value: str, correct_answer: str, answer_type: str, error_logic: str) -> bool:
    el = (error_logic or "").strip()
    if len(el) < 10:
        return True  # every distractor needs a concrete school-level mistake description
    if _GARBAGE_RE.match((value or "").strip()):
        return True

    at = (answer_type or "").lower()
    if at not in _NUMERIC_TYPES:
        return False

    if _looks_multipart(value) or _looks_multipart(correct_answer):
        return False

    try:
        c = float(str(correct_answer).replace(",", "."))
        d = float(str(value).replace(",", "."))
        denom = max(abs(c), 1.0)
        if abs(d - c) / denom > 100:
            return True
    except ValueError:
        pass
    return False


def _solves_question(value: str, question: str, answer_type: str) -> Optional[bool]:
    """True if distractor satisfies the question (must reject). None = unknown."""
    at = (answer_type or "").lower()
    core = _extract_relation_core(value) or value

    if at in ("text", "open_text", "coordinate"):
        if _looks_numeric_school_answer(value) or _INEQ_RE.search(value):
            from src.pipeline.answer_sympy import try_validate_expression_answer

            if re.search(r"сравните", question or "", re.I) and _INEQ_RE.search(core):
                return try_validate_expression_answer(question, core)
            if _looks_numeric_school_answer(core):
                return try_validate_answer_for_question(question, core, "fraction")
        return None

    if _looks_multipart(value):
        return None

    if _INEQ_RE.search(value) or (
        at == "expression" and re.search(r"сравните", question or "", re.I)
    ):
        from src.pipeline.answer_sympy import try_validate_expression_answer

        result = try_validate_expression_answer(question, core)
        if result is not None:
            return result

    if at in ("expression", "fraction", "exact_number", "decimal"):
        return try_validate_answer_for_question(question, core, at)

    if at == "equation_solution":
        return _try_validate_equation_answer(question, core)

    if at == "inequality":
        from src.pipeline.answer_sympy import try_validate_expression_answer

        return try_validate_expression_answer(question, core)

    return None


def _collision_with_correct(val: str, correct_answer: str, answer_type: str) -> bool:
    return values_collide_for_distractor(val, correct_answer, answer_type)


def _value_parts(s: str) -> list[str]:
    """Разбить многозначный ответ («x = 2,5; x = -2,5») на нормализованные части."""
    return [n for n in (_norm(p) for p in re.split(r"[;]", s or "")) if n]


def _is_proper_subset_of_correct(val: str, correct_answer: str, answer_type: str) -> bool:
    """Дистрактор — часть правильного ответа, а не ошибка.

    «Взял только один корень из двух» даёт `x = 2,5` при верном `x = 2,5; x = -2,5`.
    Полной коллизии нет, поэтому прежний гейт такой вариант пропускал — и ученик
    получал вопрос, где второй вариант тоже верен, просто неполон. Для MCQ это
    хуже обычного брака: неправильного ответа там, по сути, нет.

    Отбраковываем только строгое подмножество: равный набор — это коллизия
    (её ловит `_collision_with_correct`), а лишняя часть — уже другая ошибка.
    """
    if (answer_type or "").lower() in ("text", "open_text"):
        return False
    correct_parts = _value_parts(correct_answer)
    if len(correct_parts) < 2:
        return False
    val_parts = _value_parts(val)
    if not val_parts or len(val_parts) >= len(correct_parts):
        return False
    return set(val_parts).issubset(set(correct_parts))


@dataclass
class DistractorCheck:
    ok: bool
    reason: str = "ok"


def _peer_collision(val: str, prev: str, answer_type: str) -> bool:
    """Distractors must be distinct wrong options — not sympy-loose equivalent."""
    if _norm(val) == _norm(prev):
        return True
    at = (answer_type or "").lower()
    # Prose text: «нет, так как …» vs «нет, потому что …» share a verdict prefix only.
    # values_collide_for_distractor strips after «, так как» — false peer hits on text.
    if at in ("text", "open_text"):
        if _looks_numeric_school_answer(val) or _looks_numeric_school_answer(prev):
            return values_collide_for_distractor(val, prev, answer_type)
        return False
    return values_collide_for_distractor(val, prev, answer_type)


def validate_distractor(
    *,
    question: str,
    value: str,
    correct_answer: str,
    answer_type: str,
    error_logic: str = "",
    accepted: Optional[list[str]] = None,
    skip_l3: bool = False,
) -> DistractorCheck:
    """Validate one distractor candidate."""
    val = (value or "").strip()
    accepted = accepted or []
    at = (answer_type or "").lower()

    if not _is_parseable(val, at):
        return DistractorCheck(ok=False, reason="parse_failed")

    if _collision_with_correct(val, correct_answer, at):
        return DistractorCheck(ok=False, reason="collision_correct")

    if _is_proper_subset_of_correct(val, correct_answer, at):
        return DistractorCheck(ok=False, reason="subset_of_correct")

    for prev in accepted:
        if _peer_collision(val, prev, at):
            return DistractorCheck(ok=False, reason="collision_peer")

    if not skip_l3:
        solves = _solves_question(val, question, at)
        if solves is True:
            return DistractorCheck(ok=False, reason="solves_question")

    if _is_implausible(val, correct_answer, at, error_logic):
        return DistractorCheck(ok=False, reason="implausible")

    return DistractorCheck(ok=True, reason="ok")


def validate_distractor_set(
    items: list[dict],
    *,
    question: str,
    correct_answer: str,
    answer_type: str,
    max_count: int = 3,
    skip_l3: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    Filter distractor dicts through L1–L4 gate.
    Returns (accepted, rejected) where rejected items have gate_reason.
    """
    accepted: list[dict] = []
    rejected: list[dict] = []
    accepted_vals: list[str] = []

    for d in items:
        val = str(d.get("value", d.get("error_logic", ""))).strip()
        el = str(d.get("error_logic", d.get("explanation", ""))).strip()
        check = validate_distractor(
            question=question,
            value=val,
            correct_answer=correct_answer,
            answer_type=answer_type,
            error_logic=el,
            accepted=accepted_vals,
            skip_l3=skip_l3,
        )
        if check.ok:
            accepted.append(d)
            accepted_vals.append(val)
            if len(accepted) >= max_count:
                break
        else:
            rejected.append({**d, "gate_reason": check.reason})

    return accepted, rejected


def stored_distractors_valid(
    dmeta: list | None,
    *,
    question: str,
    correct_answer: str,
    answer_type: str,
    min_count: int = 3,
) -> bool:
    """True if stored distractor_meta passes L1–L4 (exactly min_count items)."""
    if not isinstance(dmeta, list) or len(dmeta) < min_count:
        return False
    items = [
        {
            "value": d.get("value", ""),
            "error_logic": d.get("error_logic", d.get("explanation", "")),
        }
        for d in dmeta
        if isinstance(d, dict) and str(d.get("value", "")).strip()
    ][:6]
    if len(items) < min_count:
        return False
    accepted, rejected = validate_distractor_set(
        items,
        question=question,
        correct_answer=correct_answer,
        answer_type=answer_type,
        max_count=len(items),
    )
    return len(accepted) >= min_count and not rejected
