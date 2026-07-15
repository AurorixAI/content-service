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
    _inequalities_equivalent,
    _looks_like_algebraic_expression,
    _norm,
    _normalize_ineq_symbols,
    _parse_school_number,
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


_NUMERIC_INEQ_RE = re.compile(
    r"^([+-]?[\d.,/()\s]+)\s*(<=|>=|<|>|=|!=|≠|≤|≥)\s*([+-]?[\d.,/()\s]+)$"
)


def _parse_numeric_ineq_side(raw: str) -> Optional[float]:
    s = re.sub(r"\s+", " ", (raw or "").strip())
    return _parse_school_number(s) if s else None


def _parse_numeric_ineq_triple(s: str) -> Optional[tuple[float, str, float]]:
    core = _extract_relation_core(s) or _normalize_ineq_symbols(_strip_trailing_reasoning(s))
    m = _NUMERIC_INEQ_RE.match(core.strip())
    if not m:
        return None
    lhs = _parse_numeric_ineq_side(m.group(1))
    rhs = _parse_numeric_ineq_side(m.group(3))
    if lhs is None or rhs is None:
        return None
    return lhs, m.group(2), rhs


def _ineq_truth(lhs: float, op: str, rhs: float) -> Optional[bool]:
    op = _normalize_ineq_symbols(op)
    if op == "<":
        return lhs < rhs - 1e-12
    if op == ">":
        return lhs > rhs + 1e-12
    if op in ("≤", "<="):
        return lhs <= rhs + 1e-12
    if op in ("≥", ">="):
        return lhs >= rhs - 1e-12
    if op == "=":
        return abs(lhs - rhs) < 1e-9
    return None


def _strict_inequality_collide(val: str, correct: str) -> Optional[bool]:
    """
    Numeric inequality collide without SymPy / loose answers_equivalent.

    Collide when lhs/rhs match and both state the same truth (incl. < vs ≤ when both true).
    """
    tv = _parse_numeric_ineq_triple(val)
    tc = _parse_numeric_ineq_triple(correct)
    if tv and tc:
        l1, o1, r1 = tv
        l2, o2, r2 = tc
        if abs(l1 - l2) > 1e-9 or abs(r1 - r2) > 1e-9:
            return False
        if o1 == o2:
            return True
        t1, t2 = _ineq_truth(l1, o1, r1), _ineq_truth(l2, o2, r2)
        if t1 is not None and t2 is not None:
            return t1 == t2
        return False
    if tv or tc:
        return False
    return None


def _strict_numeric_collide(val: str, correct: str) -> Optional[bool]:
    """
    Exact numeric collide for distractor gate — no 2% answers_equivalent slack.

    Returns True/False when both parse as school numbers, else None.
    """
    sa = _parse_school_number(val)
    sb = _parse_school_number(correct)
    if sa is not None and sb is not None:
        return abs(sa - sb) < 1e-9
    return None


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
        strict = _strict_inequality_collide(val_cmp, cor_cmp)
        if strict is not None:
            return strict
        return _inequalities_equivalent(val_cmp, cor_cmp)

    if at in _NUMERIC_TYPES:
        sa, sb = _to_float_bound(val_cmp), _to_float_bound(cor_cmp)
        if sa is not None and sb is not None and abs(sa - sb) < 1e-9:
            return True
        strict = _strict_numeric_collide(val_cmp, cor_cmp)
        if strict is not None:
            return strict
        equiv = resolve_distractor_equivalence_type(val, correct, answer_type)
        return answers_equivalent(val, correct, equiv)

    if at in ("text", "open_text"):
        if _looks_numeric_school_answer(val) or _looks_numeric_school_answer(correct):
            strict = _strict_numeric_collide(val_cmp, cor_cmp)
            if strict is not None:
                return strict
            return False
        return False

    equiv = resolve_distractor_equivalence_type(val, correct, answer_type)
    return answers_equivalent(val, correct, equiv)
