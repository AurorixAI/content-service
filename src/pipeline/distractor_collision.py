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
    _split_compound_parts,
    _to_float_bound,
    answers_equivalent,
)
from src.pipeline.interval_normalizer import intervals_equivalent

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
_INTERVAL_NOTATION_RE = re.compile(r"[\[(]\s*[^;\]\)]*;\s*[^;\]\)]*\s*[\])]")
_ASSIGNMENT_CHUNK_RE = re.compile(
    r"\s*[,;]\s*(?=(?:\\(?:operatorname\{)?(?:sin|cos|tg|ctg)|"
    r"[A-Za-zА-Яа-я]|\\frac|\()[^,;=]{0,160}=)",
    re.I,
)
_SYMBOLIC_IDENTIFIER_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*\b")
_SYMBOLIC_FUNCTIONS = frozenset({"sqrt", "sin", "cos", "tan", "cot", "log", "ln", "exp"})


def _assignment_chunks(value: str) -> list[tuple[str, str]]:
    """Extract a sequence of labelled answer components when it is unambiguous."""
    chunks: list[tuple[str, str]] = []
    for part in _ASSIGNMENT_CHUNK_RE.split((value or "").strip()):
        if part.count("=") != 1:
            return []
        left, right = (piece.strip() for piece in part.split("=", 1))
        if not left or not right:
            return []
        chunks.append((left, right))
    return chunks if chunks else []


def _assignment_key(value: str) -> str | None:
    key = (value or "").lower()
    key = key.replace("\\operatorname", "").replace("\\", "")
    key = re.sub(r"[{}\s]", "", key)
    return key if re.fullmatch(r"[a-zа-яα-ω][a-zа-яα-ω0-9_]*", key, re.I) else None


def _strict_assignment_collision(val: str, correct: str) -> Optional[bool]:
    """Strictly compare a rich answer made of labelled components.

    ``answers_equivalent`` is deliberately tolerant for Smart Verify of one
    final answer.  That tolerance is unsafe for a distractor: a changed sign
    in one trigonometric component must stay a wrong option, not collapse into
    the correct multi-component answer.
    """
    left, right = _assignment_chunks(val), _assignment_chunks(correct)
    if not left and not right:
        return None
    if not left or not right or len(left) != len(right):
        return False

    left_keys = [_assignment_key(key) for key, _ in left]
    right_keys = [_assignment_key(key) for key, _ in right]
    if all(left_keys) and all(right_keys) and set(left_keys) == set(right_keys):
        left_values = {key: value for key, (_, value) in zip(left_keys, left)}
        right_values = {key: value for key, (_, value) in zip(right_keys, right)}
        pairs = [(left_values[key], right_values[key]) for key in left_values]
    else:
        pairs = [(a_value, b_value) for (_, a_value), (_, b_value) in zip(left, right)]

    return all(answers_equivalent(a_value, b_value, "expression") for a_value, b_value in pairs)


def _strict_symbolic_formula_collision(val: str, correct: str) -> Optional[bool]:
    """Compare symbolic formulae while preserving indexed variable names.

    The generic school parser intentionally treats ``m2`` as ``m * 2`` for
    pupil-facing arithmetic.  In a formula, however, ``m2``, ``T1`` and
    ``c2`` are independent physical quantities.  Protect these identifiers
    before normalisation so a genuine sign or denominator error cannot become
    a false collision with the correct formula.
    """
    if max(len(val), len(correct)) > 800 or ";" in val or ";" in correct:
        return None
    if not (
        re.fullmatch(r"[A-Za-z0-9_+\-*/^().{}\\\s]+", val)
        and re.fullmatch(r"[A-Za-z0-9_+\-*/^().{}\\\s]+", correct)
    ):
        return None

    try:
        import sympy
        from sympy.parsing.sympy_parser import parse_expr, standard_transformations
        from src.pipeline.answer_sympy import _normalize_school_expression

        identifiers = {
            token
            for token in _SYMBOLIC_IDENTIFIER_RE.findall(f"{val} {correct}")
            if token.lower() not in _SYMBOLIC_FUNCTIONS
        }
        if not identifiers:
            return None
        replacement = {
            token: f"__formula_symbol_{index}__"
            for index, token in enumerate(sorted(identifiers, key=len, reverse=True))
        }

        def parse_formula(source: str):
            protected = source
            for token, placeholder in replacement.items():
                protected = re.sub(rf"\b{re.escape(token)}\b", placeholder, protected)
            normalized = _normalize_school_expression(protected)
            local_dict = {
                placeholder: sympy.Symbol(token)
                for token, placeholder in replacement.items()
            }
            return parse_expr(
                normalized,
                transformations=standard_transformations,
                local_dict=local_dict,
                evaluate=True,
            )

        left, right = parse_formula(val), parse_formula(correct)
        return sympy.cancel(left - right) == 0
    except Exception:
        return None


def _strict_compound_solution_collision(val: str, correct: str) -> Optional[bool]:
    """Compare semicolon-delimited solution parts without loose list heuristics."""
    parts_a = _split_compound_parts(val)
    parts_b = _split_compound_parts(correct)
    if len(parts_a) < 2 or len(parts_a) != len(parts_b):
        return None
    for left, right in zip(parts_a, parts_b):
        # Coordinate/system chunks need the existing precise solution parser;
        # labelled numeric subanswers are compared as numbers.
        domain = "equation_solution" if "=" in left or "=" in right else "exact_number"
        if not answers_equivalent(left, right, domain):
            return False
    return True


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

    # A different interval boundary is a different answer.  The generic
    # inequality normalizer is intentionally permissive for answer checking,
    # but distractors must use strict set equality.
    if at == "inequality" and (
        _INTERVAL_NOTATION_RE.search(val_cmp) or _INTERVAL_NOTATION_RE.search(cor_cmp)
    ):
        interval_equal = intervals_equivalent(val_cmp, cor_cmp)
        if interval_equal is not None:
            return interval_equal

    # Historical ``exact_number`` metadata is often promoted by the caller to
    # equation_solution.  Do not let general number-list equivalence collapse
    # one changed component of a multi-part solution into the correct answer.
    if at == "equation_solution":
        compound_equal = _strict_compound_solution_collision(val_cmp, cor_cmp)
        if compound_equal is not None:
            return compound_equal
        # A multi-component candidate and a multi-component correct answer
        # with incompatible shapes cannot be the same solution set.  Do not
        # fall through to the legacy loose numeric-list matcher below.
        if ";" in val_cmp and ";" in cor_cmp:
            return False

    # A symbolic formula must be equal as an expression.  Do not run the
    # answer-verification fallback that strips assignment-like fragments and
    # can collapse a genuine algebraic sign error into the correct result.
    if at == "expression" and (
        re.search(r"[A-Za-zА-Яа-я]", val_cmp)
        or re.search(r"[A-Za-zА-Яа-я]", cor_cmp)
    ):
        formula_equal = _strict_symbolic_formula_collision(val_cmp, cor_cmp)
        if formula_equal is not None:
            return formula_equal
        from src.pipeline.answer_sympy import sympy_equivalent
        return sympy_equivalent(val_cmp, cor_cmp, "expression") is True

    if at == "expression" and re.fullmatch(r"[a-zA-Z]", cor_cmp):
        return val_cmp == cor_cmp

    if _INEQ_RE.search(val) or _INEQ_RE.search(correct):
        strict = _strict_inequality_collide(val_cmp, cor_cmp)
        if strict is not None:
            return strict
        return _inequalities_equivalent(val_cmp, cor_cmp)

    assignment_equal = _strict_assignment_collision(val_cmp, cor_cmp)
    if assignment_equal is not None:
        # A lone ``x = …`` is a subset of a multi-root answer, not a new
        # independent rich-answer format.  Existing equation-solution logic
        # correctly treats it as a collision with the complete solution set.
        if not (at == "equation_solution" and ";" in cor_cmp and ";" not in val_cmp):
            return assignment_equal

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
