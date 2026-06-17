"""SymPy-backed answer comparison for verify pipeline."""
from __future__ import annotations

import logging
import random
import re
from typing import Optional

log = logging.getLogger(__name__)

_SYMBOL_NAMES = "abcdefghijklmnopqrsuvwxyz"


def _latexish_to_sympy(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.replace("√", "sqrt").replace("×", "*").replace("·", "*")
    s = s.replace("^", "**")
    s = re.sub(r"\\sqrt\{([^}]+)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"((\1)/(\2))", s)
    s = re.sub(r"\$", "", s)
    s = re.sub(r"\\left|\\right", "", s)
    s = re.sub(r"\\cdot", "*", s)
    s = re.sub(r"\\times", "*", s)
    s = re.sub(r",(\d)", r".\1", s)
    # implicit multiplication: 2n, 2(x+1), )(
    s = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", s)
    s = re.sub(r"(\d)\s*\(", r"\1*(", s)
    s = re.sub(r"\)\s*\(", r")*(", s)
    s = re.sub(r"sqrt\*\(", "sqrt(", s)
    return s


def split_answer_parts(answer: str) -> list[str]:
    """Split multi-part answers (а) б) в); ...)."""
    s = (answer or "").strip()
    if not s:
        return []
    parts = re.split(r"\s*;\s*", s)
    cleaned: list[str] = []
    for p in parts:
        p = re.sub(r"^[абвгдежзийклмнопрстуфхцчшщъыьэюя]\)\s*", "", p, flags=re.I)
        p = re.sub(r"^\d+\)\s*", "", p)
        p = p.strip()
        if p:
            cleaned.append(p)
    return cleaned if cleaned else [s]


def parse_expr(expr_str: str):
    """Parse math string to SymPy expression, or None."""
    try:
        import sympy
        from sympy.parsing.sympy_parser import (
            implicit_multiplication_application,
            parse_expr,
            standard_transformations,
        )
    except ImportError:
        return None

    raw = _latexish_to_sympy(expr_str)
    if not raw:
        return None

    transformations = standard_transformations + (implicit_multiplication_application,)
    try:
        from sympy import sqrt

        local_dict = {"sqrt": sqrt}
        return parse_expr(
            raw,
            transformations=transformations,
            evaluate=True,
            local_dict=local_dict,
        )
    except Exception:
        pass
    try:
        from sympy.parsing.latex import parse_latex

        return parse_latex(expr_str)
    except Exception:
        pass
    try:
        return sympy.sympify(raw.replace("**", "^"))
    except Exception:
        return None


def _exprs_equivalent(a, b) -> bool:
    import sympy

    try:
        if sympy.simplify(a - b) == 0:
            return True
    except Exception:
        pass
    try:
        if sympy.Eq(sympy.simplify(a), sympy.simplify(b)):
            return True
    except Exception:
        pass
    return False


def monte_carlo_equivalent(a_str: str, b_str: str, *, trials: int = 6) -> Optional[bool]:
    """
    True/False if expressions likely equivalent/different via random substitution.
    None if cannot parse or compare.
    """
    a = parse_expr(a_str)
    b = parse_expr(b_str)
    if a is None or b is None:
        return None

    try:
        from sympy.core.expr import Expr
    except ImportError:
        Expr = object  # type: ignore

    if not isinstance(a, Expr) or not isinstance(b, Expr):
        return None

    if _exprs_equivalent(a, b):
        return True

    try:
        import sympy
        from sympy import N
    except ImportError:
        return None

    syms = list(a.free_symbols | b.free_symbols)
    if not syms:
        try:
            return abs(float(N(a)) - float(N(b))) < 1e-6
        except Exception:
            return None

    rng = random.Random(42)
    for _ in range(trials):
        subs = {s: rng.randint(2, 11) for s in syms}
        try:
            va = complex(N(a.subs(subs)))
            vb = complex(N(b.subs(subs)))
            if abs(va - vb) > 1e-5:
                return False
        except Exception:
            return None
    return True


def sympy_equivalent(a: str, b: str, answer_type: str = "") -> Optional[bool]:
    """
    True = mathematically same, False = different, None = cannot decide.
    """
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return None
    if a == b:
        return True

    pa, pb = split_answer_parts(a), split_answer_parts(b)
    if len(pa) == len(pb) and len(pa) > 1:
        results = [sympy_equivalent(x, y, answer_type) for x, y in zip(pa, pb)]
        if any(r is False for r in results):
            return False
        if all(r is True for r in results):
            return True
        return None

    ea, eb = parse_expr(a), parse_expr(b)
    if ea is not None and eb is not None:
        if _exprs_equivalent(ea, eb):
            return True
        mc = monte_carlo_equivalent(a, b)
        if mc is not None:
            return mc
        return False

    mc = monte_carlo_equivalent(a, b)
    if mc is not None:
        return mc
    return None


def sympy_numeric_equal(a: str, b: str) -> Optional[bool]:
    ea, eb = parse_expr(a), parse_expr(b)
    if ea is None or eb is None:
        return None
    try:
        from sympy import N

        return abs(float(N(ea)) - float(N(eb))) < 1e-6
    except Exception:
        return None


def try_validate_answer_for_question(question: str, answer: str, answer_type: str) -> Optional[bool]:
    """
    When possible, check answer against expression extracted from question.
    True = answer matches simplified target, False = mismatch, None = unknown.
    """
    q = (question or "").strip()
    ans = (answer or "").strip()
    if not q or not ans:
        return None

    at = (answer_type or "").lower()
    if at not in ("expression", "fraction", "exact_number", "decimal"):
        return None

    # Last math-heavy line in question (after split_compound often the sub-expression)
    lines = [ln.strip() for ln in q.splitlines() if ln.strip()]
    expr_line = ""
    for ln in reversed(lines):
        if re.search(r"[0-9a-z\\$+\-*/^()=]", ln, re.I):
            expr_line = ln
            break
    if not expr_line:
        expr_line = lines[-1] if lines else q

    expr_line = re.sub(r"^[абвгдежзийклмнопрстуфхцчшщъыьэюя]\)\s*", "", expr_line, flags=re.I)
    expr_line = expr_line.rstrip(";").strip()

    target = parse_expr(expr_line)
    if target is None:
        return None

    try:
        import sympy
        from sympy import N

        simplified = sympy.simplify(target)
        answer_expr = parse_expr(ans)
        if answer_expr is None:
            return None
        if _exprs_equivalent(simplified, answer_expr):
            return True
        mc = monte_carlo_equivalent(str(simplified), ans)
        if mc is True:
            return True
        if mc is False:
            return False
        try:
            return abs(float(N(simplified)) - float(N(answer_expr))) < 1e-5
        except Exception:
            return None
    except Exception:
        return None
