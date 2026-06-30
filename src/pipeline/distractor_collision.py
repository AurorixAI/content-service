"""
Strict distractor value collision — separate from answer verification equivalence.

Answer verification may use loose matching (substring, cross-type probes).
Distractor gate must NOT reject plausible wrong options due to those heuristics.
"""
from __future__ import annotations

import re
from typing import Optional

from src.pipeline.answer_verify import (
    _extract_int_list,
    _looks_like_algebraic_expression,
    _norm,
    _normalize_ineq_symbols,
    _to_float_bound,
    answers_equivalent,
)

_NUMERIC_TYPES = frozenset({"exact_number", "decimal", "fraction"})
_INEQ_RE = re.compile(r"(?:<=|>=|≤|≥|!=|≠|<|>)")
_MIXED_FRAC_RE = re.compile(r"^\d+\s+\d+/\d+$")
_FRAC_RE = re.compile(r"^\d+/\d+$")
_TRAILING_REASON_RE = re.compile(
    r",\s*(?:так как|потому что|так что|поскольку|значит|т\.?\s*к\.?).*$",
    re.I,
)
_NUMERIC_TEXT_RE = re.compile(
    r"^[\d\s.,+\-]+(?:/\d+)?(?:\s+\d+/\d+)?$",
)


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


def _comparison_value(val: str) -> str:
    return _extract_relation_core(val) or _strip_trailing_reasoning(val) or (val or "").strip()


def _looks_numeric_school_answer(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return False
    if _NUMERIC_TEXT_RE.match(s):
        return True
    if _MIXED_FRAC_RE.match(s) or _FRAC_RE.match(s):
        return True
    if _extract_relation_core(s):
        return True
    return False


def _has_fraction_syntax(s: str) -> bool:
    s = (s or "").strip()
    if "/" in s:
        return True
    return bool(_MIXED_FRAC_RE.match(s))


def resolve_distractor_equivalence_type(val: str, correct: str, answer_type: str) -> str:
    """Pick one equivalence domain — never cross-probe exact_number on fractions."""
    at = (answer_type or "").lower()
    if at in ("text", "open_text", "coordinate", "multiple_choice"):
        return at
    if at == "inequality" or _INEQ_RE.search(val) or _INEQ_RE.search(correct):
        return "inequality"
    if at in _NUMERIC_TYPES:
        return "fraction" if _has_fraction_syntax(val) or _has_fraction_syntax(correct) else at
    if at == "set":
        if _looks_like_algebraic_expression(val) or _looks_like_algebraic_expression(correct):
            return "expression"
        if _extract_int_list(val) is not None and _extract_int_list(correct) is not None:
            return "set"
        return at
    if at in ("expression", "equation_solution"):
        if _has_fraction_syntax(val) or _has_fraction_syntax(correct):
            return "fraction"
        return at
    return at


def values_collide_for_distractor(val: str, correct: str, answer_type: str) -> bool:
    """
    True when distractor value must be rejected as equal to the correct answer.

    Stricter than general answers_equivalent: no substring, no cross-type probes.
    """
    val_cmp = _comparison_value(val)
    cor_cmp = _comparison_value(correct)
    if not val_cmp or not cor_cmp:
        return False
    if _norm(val_cmp) == _norm(cor_cmp):
        return True

    at = (answer_type or "").lower()

    if at == "expression" and re.fullmatch(r"[a-zA-Z]", cor_cmp):
        return val_cmp == cor_cmp

    if _INEQ_RE.search(val) or _INEQ_RE.search(correct):
        return answers_equivalent(val_cmp, cor_cmp, "inequality")

    if at in _NUMERIC_TYPES:
        sa, sb = _to_float_bound(val_cmp), _to_float_bound(cor_cmp)
        if sa is not None and sb is not None and abs(sa - sb) < 1e-9:
            return True
        equiv = resolve_distractor_equivalence_type(val, correct, answer_type)
        return answers_equivalent(val, correct, equiv)

    if at in ("text", "open_text"):
        if _looks_numeric_school_answer(val) or _looks_numeric_school_answer(correct):
            equiv = resolve_distractor_equivalence_type(val, correct, "fraction")
            return answers_equivalent(val, correct, equiv)
        return False

    equiv = resolve_distractor_equivalence_type(val, correct, answer_type)
    return answers_equivalent(val, correct, equiv)
