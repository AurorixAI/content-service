"""
Gemini + SymPy answer verification before distractor generation.

Policy (max accuracy):
  1. Gemini Flash re-solves; compare with stored (string + SymPy).
  2. On mismatch → Gemini Pro second opinion (dual consensus).
  3. Auto-correct ONLY when Flash ≈ Pro AND SymPy/question validation favours consensus.
  4. SymPy says stored ≈ consensus → never change.
  5. SymPy favours stored → verify_conflict (keep stored, human review).
  6. No SymPy confirmation for correction → verify_unresolved (no auto-fix).
  7. Flash matches but stored fails SymPy check → verify_unresolved.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from src.pipeline.answer_sympy import (
    monte_carlo_equivalent,
    parse_expr,
    split_answer_parts,
    sympy_equivalent,
    try_validate_answer_for_question,
    back_substitute_roots,
    _normalize_school_expression,
    _normalize_decimal_commas,
    _fraction_list_parts,
    _parse_scientific_value,
)
from src.pipeline.interval_normalizer import intervals_equivalent as _intervals_equivalent

log = logging.getLogger(__name__)

_VERIFIABLE_TYPES = frozenset({
    "exact_number", "decimal", "fraction", "expression",
    "equation_solution", "inequality", "set", "multiple_choice",
})

_SKIP_VERIFY_RE = re.compile(
    r"докажите|доказать|изобразите|постройте|построить|"
    r"чертёж|чертеж|график функции|заполните таблиц",
    re.I,
)

_INCOMPLETE_Q_RE = re.compile(
    r"^(упростите|вычислите|найдите|сократите|представьте|выполните|разложите)\s*(выражение|дробь)?\s*:?\s*$",
    re.I,
)


@dataclass
class AnswerVerifyResult:
    match: bool
    gemini_answer: str = ""
    gemini_answer_pro: str = ""
    stored_answer: str = ""
    final_answer: str = ""
    verified: bool = False
    corrected: bool = False
    skip_distractors: bool = False
    skip_reason: str = ""
    tags_patch: dict = field(default_factory=dict)


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    subs = str.maketrans("₀₁₂₃₄₅₆₇₈₉ₙ", "0123456789n")
    s = s.translate(subs)
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.replace("{", "").replace("}", "").replace("$", "")
    s = s.replace("\\sqrt", "sqrt").replace("\\frac", "")
    s = re.sub(r"\s+", "", s)
    s = s.replace(",", ".")
    s = re.sub(r"^\d+\)", "", s)
    s = re.sub(r"^[абвг]\)", "", s)
    s = re.sub(r"^x[_₀₁₂]?=", "x=", s)
    s = re.sub(r"^x=", "", s)
    s = re.sub(r"^y=", "", s)
    return s


def _extract_numbers(s: str) -> list[float]:
    s = _norm(s)
    nums: list[float] = []
    for m in re.finditer(r"-?\d+\.?\d*", s):
        try:
            nums.append(float(m.group()))
        except ValueError:
            pass
    return nums


def _try_fraction(s: str) -> Optional[float]:
    s = (s or "").strip().replace(",", ".")
    v = _parse_school_number(s)
    if v is not None:
        return v
    if "/" in s and "=" not in s:
        parts = s.split("/", 1)
        if len(parts) == 2:
            try:
                return float(Fraction(int(parts[0].strip()), int(parts[1].strip())))
            except (ValueError, ZeroDivisionError):
                pass
    try:
        return float(s)
    except ValueError:
        return None


_MIXED_FRAC_RE = re.compile(r"^(-?\d+)\s+(\d+)/(\d+)$")
_SIMPLE_FRAC_RE = re.compile(r"^(-?\d+)/(\d+)$")


def _parse_school_number(s: str) -> Optional[float]:
    """Parse school notation: decimals, fractions, mixed fractions (-1 1/3)."""
    s = (s or "").strip().replace(",", ".")
    if not s:
        return None
    m = _MIXED_FRAC_RE.match(s)
    if m:
        whole, n, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if d == 0:
            return None
        sign = -1 if whole < 0 else 1
        return whole + sign * n / d
    m = _SIMPLE_FRAC_RE.match(s)
    if m:
        try:
            return float(Fraction(int(m.group(1)), int(m.group(2))))
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_surd_text(s: str) -> str:
    """√21, \\sqrt{2}, 3*√3 → sympy-safe sqrt forms."""
    s = (s or "").strip()
    s = re.sub(r"\\sqrt\{([^}]+)\}", r"sqrt(\1)", s)
    s = s.replace("√", "sqrt")
    s = re.sub(r"sqrt(\d+)", r"sqrt(\1)", s)
    s = re.sub(r"(\d)\*sqrt\(", r"\1*sqrt(", s)
    s = re.sub(r"(\d)sqrt\(", r"\1*sqrt(", s)
    return s


def _eval_surd_arithmetic(s: str) -> Optional[float]:
    """Evaluate school surd expressions like 7/2 - sqrt(41)/2 without SymPy."""
    import math

    s = _normalize_surd_text(s)
    if not s or "sqrt" not in s.lower():
        return None
    expr = re.sub(r"sqrt\((\d+)\)", r"math.sqrt(\1)", s, flags=re.I)
    if not re.fullmatch(r"[\d.+\-*/()math.sqrt ]+", expr):
        return None
    try:
        return float(eval(expr, {"__builtins__": {}}, {"math": math}))
    except Exception:
        return None


def _expr_to_float(s: str) -> Optional[float]:
    """Parse school math text (fractions, surds) to float via SymPy."""
    s = _normalize_surd_text((s or "").strip())
    if not s:
        return None
    v = _parse_school_number(s)
    if v is not None:
        return v
    v = _eval_surd_arithmetic(s)
    if v is not None:
        return round(v, 8)
    try:
        from sympy import N

        from src.pipeline.answer_sympy import _latexish_to_sympy, parse_expr

        for raw in (s, _latexish_to_sympy(s)):
            expr = parse_expr(raw)
            if expr is not None:
                val = N(expr)
                if val.is_real:
                    return round(float(val), 8)
    except Exception:
        pass
    return None


def _split_equation_solution_chunks(s: str) -> list[str]:
    """Split roots: ';' lists, or 'x_1 = …, x_2 = …' comma lists."""
    s = (s or "").strip()
    if not s:
        return []
    # Multiple solution pairs: x_1=…, x_2=…; x_1=…, x_2=…
    if re.search(r"x_1\s*=", s, re.I) and ";" in s:
        return [c.strip() for c in re.split(r"\s*;\s*", s) if c.strip()]
    if re.search(r"[x-zA-Z][_₀₁₂\d]*\s*=", s) and "," in s:
        chunks = re.split(r",\s*(?=[x-zA-Z])", s)
        if len(chunks) >= 2:
            return [c.strip() for c in chunks if c.strip()]
    return [c.strip() for c in re.split(r"\s*;\s*", s) if c.strip()]


_COORD_PAIR_RE = re.compile(r"\(\s*([^;)]+?)\s*;\s*([^)]+?)\s*\)")


def _parse_coordinate_pairs(s: str) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for m in _COORD_PAIR_RE.finditer(s or ""):
        x = _expr_to_float(m.group(1))
        y = _expr_to_float(m.group(2))
        if x is not None and y is not None:
            pairs.append((round(x, 4), round(y, 4)))
    return pairs


def _parse_indexed_variable_pairs(s: str) -> list[tuple[float, float]]:
    """x_1 = a, x_2 = b; x_1 = c, x_2 = d → [(a,b), (c,d)]."""
    pairs: list[tuple[float, float]] = []
    for chunk in re.split(r"\s*;\s*", s or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        m1 = re.search(r"x_1\s*=\s*([^,;]+)", chunk, re.I)
        m2 = re.search(r"x_2\s*=\s*(.+)$", chunk, re.I)
        if m1 and m2:
            x = _expr_to_float(m1.group(1))
            y = _expr_to_float(m2.group(1))
            if x is not None and y is not None:
                pairs.append((round(x, 4), round(y, 4)))
    return pairs


def _comma_separated_numeric_roots(s: str) -> list[float]:
    """Bare '3.79, 0.21' or '2, 2.5' without x= prefix."""
    s = (s or "").strip()
    if not s or re.search(r"[x-zA-Z]\s*=", s, re.I) or "(" in s:
        return []
    if "," not in s:
        return []
    vals: list[float] = []
    for part in s.split(","):
        v = _expr_to_float(part.strip())
        if v is not None:
            vals.append(round(v, 6))
    return sorted(vals) if len(vals) >= 2 else []


def _parse_labeled_variable_pairs(s: str) -> list[tuple[float, float]]:
    """x = 4, y = 3 or u = 43/9, v = -10/9 → [(4, 3)]."""
    s = (s or "").strip()
    if not s or "(" in s and ";" in s:
        return []
    parts = re.split(r",\s*(?=[a-zA-Z_])", s)
    vals: list[float] = []
    for part in parts:
        m = re.match(r"^[a-zA-Z_]\w*\s*=\s*(.+)$", part.strip())
        if not m:
            return []
        v = _expr_to_float(m.group(1).strip())
        if v is None:
            return []
        vals.append(round(v, 4))
    if len(vals) >= 2:
        return [(vals[0], vals[1])]
    return []


def _parse_semicolon_xy_pairs(s: str) -> list[tuple[float, float]]:
    """Parse semicolon-separated variable pairs: 'x=5; y=3' or 'x=4; y=8 или x=-2; y=-4'.
    Also handles plain numeric semicolon pairs like 'x=3; y=2 или x=2; y=3' as coord tuples.
    Returns list of (x_val, y_val) tuples.
    """
    s = (s or "").strip()
    # Split on ' или ' first
    or_chunks = re.split(r"\s+или\s+", s)
    result: list[tuple[float, float]] = []
    for chunk in or_chunks:
        chunk = chunk.strip()
        # Match pattern: var=val; var=val (optional more)
        pairs_in_chunk: list[float] = []
        for m in re.finditer(r"[a-zA-Z_]\w*\s*=\s*([^;,]+)", chunk):
            v = _expr_to_float(m.group(1).strip())
            if v is None:
                break
            pairs_in_chunk.append(round(v, 4))
        if len(pairs_in_chunk) >= 2:
            result.append(tuple(pairs_in_chunk[:2]))
        else:
            return []
    return result


def _extract_numbers_sorted(s: str) -> list[float]:
    """Extract all numbers from any text (including prose answers).
    E.g. 'мастер 60; ученик 40' → [40.0, 60.0]
    Used for comparing word-problem answers that have same numbers but different text.
    """
    nums = []
    for m in re.finditer(r"-?\d+(?:[.,]\d+)?", s or ""):
        try:
            nums.append(round(float(m.group().replace(",", ".")), 4))
        except ValueError:
            pass
    return sorted(nums)



def _coordinate_system_equivalent(a: str, b: str) -> bool:
    pa = (
        _parse_coordinate_pairs(a)
        or _parse_indexed_variable_pairs(a)
        or _parse_labeled_variable_pairs(a)
    )
    pb = (
        _parse_coordinate_pairs(b)
        or _parse_indexed_variable_pairs(b)
        or _parse_labeled_variable_pairs(b)
    )
    if not pa or not pb or len(pa) != len(pb):
        return False
    pa = sorted(pa)
    pb = sorted(pb)
    return all(abs(x[0] - y[0]) < 1e-2 and abs(x[1] - y[1]) < 1e-2 for x, y in zip(pa, pb))


def _solution_value_set(s: str) -> list[float]:
    """Numeric roots from equation_solution text (incl. ± and bare lists)."""
    cs = _comma_separated_numeric_roots(s)
    if cs:
        return cs
    vals: list[float] = []
    for part in _equation_solution_parts(s):
        part = part.strip()
        m = re.match(r"^([x-zA-Z][_₀₁₂\d]*)\s*=\s*(.+)$", part, re.I)
        num_s = m.group(2).strip() if m else part
        v = _expr_to_float(num_s)
        if v is not None:
            vals.append(round(v, 8))
    return sorted(vals)


def _normalize_pm_text(s: str) -> str:
    """LaTeX \\pm → Unicode ± for parsing."""
    return (s or "").replace(r"\pm", "±").replace("\\pm", "±")


def _expand_pm_solutions(s: str) -> list[str]:
    """x = ±3/2 or x = \\pm 3/2 → [x = 3/2, x = -3/2]"""
    s = _normalize_pm_text(_normalize_surd_text((s or "").strip()))
    m = re.match(r"^([x-zA-Z])\s*=\s*±\s*(.+)$", s, re.I)
    if not m:
        return [s]
    var, val = m.group(1), m.group(2).strip()
    return [f"{var} = {val}", f"{var} = -{val}"]


_ITEM_PREFIX_RE = re.compile(r"^[а-гдежз]\)\s*|^\d+\)\s*", re.I)


def _strip_item_prefix(s: str) -> str:
    return _ITEM_PREFIX_RE.sub("", (s or "").strip())


def _split_compound_parts(s: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"\s*;\s*", s or ""):
        chunk = _strip_item_prefix(chunk.strip())
        if chunk:
            parts.append(chunk)
    return parts


def _bare_pm_value_set(s: str) -> list[float]:
    """5 ± 2\\sqrt{2} → sorted numeric roots."""
    s = _normalize_pm_text(_normalize_surd_text((s or "").strip()))
    m = re.match(r"^(.+?)\s*±\s*(.+)$", s)
    if not m:
        return []
    base, delta = m.group(1).strip(), m.group(2).strip()
    hi = _expr_to_float(f"{base}+{delta}")
    lo = _expr_to_float(f"{base}-{delta}")
    if hi is None or lo is None:
        return []
    return sorted([round(lo, 6), round(hi, 6)])


def _compound_parts_equivalent(a: str, b: str) -> bool:
    pa = _split_compound_parts(a)
    pb = _split_compound_parts(b)
    if len(pa) < 2 or len(pa) != len(pb):
        return False
    used: set[int] = set()
    for x in pa:
        found = False
        for i, y in enumerate(pb):
            if i in used:
                continue
            if _single_equation_solution_equivalent(x, y):
                used.add(i)
                found = True
                break
        if not found:
            return False
    return True


def _single_equation_solution_equivalent(a: str, b: str) -> bool:
    if _coordinate_system_equivalent(a, b):
        return True
    if _equation_solution_sets_equivalent(a, b):
        return True
    va = _bare_pm_value_set(a)
    vb = _bare_pm_value_set(b) or _solution_value_set(b)
    if va and vb and len(va) == len(vb):
        return all(abs(x - y) < 1e-2 for x, y in zip(va, sorted(vb)))
    vb2 = _bare_pm_value_set(b)
    va2 = _bare_pm_value_set(a)
    if va2 and _solution_value_set(b):
        vb3 = _solution_value_set(b)
        if len(va2) == len(vb3):
            return all(abs(x - y) < 1e-2 for x, y in zip(va2, vb3))
    return False


def _equation_solution_parts(s: str) -> list[str]:
    parts: list[str] = []
    for chunk in _split_equation_solution_chunks(s):
        parts.extend(_expand_pm_solutions(chunk))
    return parts or [s]


def stored_answer_matches_compute(
    stored: str,
    *candidates: str,
    answer_type: str = "",
) -> bool:
    """True if stored answer is mathematically equivalent to any computed candidate."""
    stored = (stored or "").strip()
    if not stored:
        return False
    for cand in candidates:
        c = (cand or "").strip()
        if c and answers_equivalent(stored, c, answer_type):
            return True
    return False


def _equation_solution_sets_equivalent(a: str, b: str) -> bool:
    """Compare equation solution sets (incl. ± notation and bare numeric lists)."""
    va = _solution_value_set(a)
    vb = _solution_value_set(b)
    if va and vb and len(va) == len(vb):
        if all(abs(x - y) < 2e-2 for x, y in zip(va, vb)):
            return True

    pa = _equation_solution_parts(a)
    pb = _equation_solution_parts(b)
    if len(pa) != len(pb):
        # subset check for combined answers
        if len(pa) == 1 and len(pb) == 2:
            pa, pb = pb, pa
        if len(pa) != len(pb):
            return False
    used: set[int] = set()
    for x in pa:
        found = False
        for i, y in enumerate(pb):
            if i in used:
                continue
            if _norm(x) == _norm(y) or sympy_equivalent(x, y, "equation_solution") is True:
                used.add(i)
                found = True
                break
        if not found:
            return False
    return True


def _normalize_ineq_symbols(s: str) -> str:
    s = (s or "").strip()
    for old, new in (
        ("⩽", "<="), ("⩾", ">="), ("≤", "<="), ("≥", ">="),
        ("\\leqslant", "<="), ("\\geqslant", ">="),
        ("\\le", "<="), ("\\ge", ">="),
        (" или ", ";"),
    ):
        s = s.replace(old, new)
    return s


def _to_float_bound(s: str) -> Optional[float]:
    raw = _normalize_school_expression(_normalize_decimal_commas((s or "").strip()))
    if not raw:
        return None
    mixed = re.match(r"^(\d+)\((\d+)/(\d+)\)$", raw.replace(" ", ""))
    if mixed:
        try:
            return float(Fraction(int(mixed.group(1)))) + float(
                Fraction(int(mixed.group(2)), int(mixed.group(3)))
            )
        except Exception:
            pass
    try:
        if "/" in raw and not re.search(r"[a-z]", raw, re.I):
            return float(Fraction(raw))
    except Exception:
        pass
    ex = parse_expr(raw)
    if ex is not None:
        try:
            from sympy import N
            return float(N(ex))
        except Exception:
            pass
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _parse_single_inequality(s: str) -> Optional[tuple[str, str, float]]:
    s = _normalize_ineq_symbols(s).strip()
    m = re.match(r"^([a-zA-Z])(?:_\d+)?\s*(<=|>=|<|>)\s*(.+)$", s, re.I)
    if not m:
        return None
    val = _to_float_bound(m.group(3))
    if val is None:
        return None
    return m.group(1).lower(), m.group(2), val


def _numeric_inequality_equivalent(a: str, b: str) -> bool:
    """21 > 2 style inequalities without a variable."""
    m1 = re.match(
        r"^([+-]?[\d.,/()]+)\s*(<=|>=|<|>)\s*([+-]?[\d.,/()]+)$",
        _normalize_ineq_symbols(a).strip(),
    )
    m2 = re.match(
        r"^([+-]?[\d.,/()]+)\s*(<=|>=|<|>)\s*([+-]?[\d.,/()]+)$",
        _normalize_ineq_symbols(b).strip(),
    )
    if not m1 or not m2 or m1.group(2) != m2.group(2):
        return False
    lhs1, rhs1 = _to_float_bound(m1.group(1)), _to_float_bound(m1.group(3))
    lhs2, rhs2 = _to_float_bound(m2.group(1)), _to_float_bound(m2.group(3))
    if None in (lhs1, rhs1, lhs2, rhs2):
        return False
    return abs(lhs1 - lhs2) < 0.02 and abs(rhs1 - rhs2) < 0.02


def _parse_interval_inequality(s: str) -> Optional[tuple[str, float, float]]:
    s = re.sub(r"\s+", "", _normalize_ineq_symbols(s))
    m = re.match(
        r"^([+-]?[\d.,/()]+)(<=)([a-zA-Z])(<=)([+-]?[\d.,/()]+)$",
        s,
        re.I,
    )
    if m:
        lo = _to_float_bound(m.group(1))
        hi = _to_float_bound(m.group(5))
        if lo is not None and hi is not None:
            return m.group(3).lower(), lo, hi
    m = re.match(
        r"^\(([a-zA-Z])(>=)([^)]+)\)&\(\1(<=)([^)]+)\)$",
        s,
        re.I,
    )
    if m:
        lo = _to_float_bound(m.group(3))
        hi = _to_float_bound(m.group(5))
        if lo is not None and hi is not None:
            return m.group(1).lower(), lo, hi
    return None


def _normalize_sympy_rel_format(s: str) -> str:
    s = (s or "").strip()
    for rel, op in (
        ("GreaterEqual", ">="),
        ("LessEqual", "<="),
        ("Greater", ">"),
        ("Less", "<"),
    ):
        m = re.match(rf"^{rel}\((.+),\s*(.+)\)$", s, re.I)
        if m:
            return f"{m.group(1).strip()} {op} {m.group(2).strip()}"
    return s


def _single_inequalities_equivalent(a: str, b: str) -> bool:
    a = _normalize_sympy_rel_format(a)
    b = _normalize_sympy_rel_format(b)
    if _numeric_inequality_equivalent(a, b):
        return True
    pa = _parse_single_inequality(a)
    pb = _parse_single_inequality(b)
    if pa and pb:
        return pa[0] == pb[0] and pa[1] == pb[1] and abs(pa[2] - pb[2]) < 0.02
    ia = _parse_interval_inequality(a)
    ib = _parse_interval_inequality(b)
    if ia and ib:
        return (
            ia[0] == ib[0]
            and abs(ia[1] - ib[1]) < 0.02
            and abs(ia[2] - ib[2]) < 0.02
        )
    return False


def _inequality_parts(s: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"[;]", _normalize_ineq_symbols(s)):
        chunk = re.sub(r"^[а-я]\)\s*", "", chunk.strip(), flags=re.I)
        if chunk:
            parts.append(chunk)
    return parts


def _inequalities_equivalent(a: str, b: str) -> bool:
    if _single_inequalities_equivalent(a, b):
        return True
    pa, pb = _inequality_parts(a), _inequality_parts(b)
    if not pa or len(pa) != len(pb):
        return False
    used: set[int] = set()
    for x in pa:
        found = False
        for i, y in enumerate(pb):
            if i in used:
                continue
            if _single_inequalities_equivalent(x, y) or _norm(x) == _norm(y):
                used.add(i)
                found = True
                break
        if not found:
            return False
    return True


def _numeric_parts_equivalent(a: str, b: str, *, tol: float = 0.02) -> bool:
    pa = split_answer_parts(a)
    pb = split_answer_parts(b)
    if len(pa) < 2 or len(pa) != len(pb):
        return False
    vals_a: list[float] = []
    vals_b: list[float] = []
    for part in pa:
        v = _to_float_bound(part) if "/" in part or re.search(r"\d", part) else _try_fraction(part)
        if v is None:
            return False
        vals_a.append(v)
    for part in pb:
        v = _to_float_bound(part) if "/" in part or re.search(r"\d", part) else _try_fraction(part)
        if v is None:
            return False
        vals_b.append(v)
    vals_a.sort()
    vals_b.sort()
    return all(abs(x - y) <= max(tol, tol * max(abs(x), 1.0)) for x, y in zip(vals_a, vals_b))


def _has_free_parameters(s: str) -> bool:
    """True when answer contains given parameters (a, b, v_1, n, m, …), not just roots."""
    text = (s or "").strip()
    body = text
    m = re.match(r"^(x|y|t|z)(_\d+)?\s*=", text, re.I)
    if m:
        body = text.split("=", 1)[1]
    low = body.lower()
    if re.search(r"(?<![a-z])([abcefghijklnopqrstuvwyz]|v\d|v_\d)(?![a-z])", low):
        return True
    if re.search(r"\bn\b", low) and re.search(r"\bm\b", low):
        return True
    return False


_UNIVERSAL_DOMAIN_RE = re.compile(
    r"^(?:все\s+|люб(?:ое|ые)\s+)?(?:действительные\s+)?числ|reals?|universal\s*set|"
    r"любое\s+(?:число|значение)|любые\s+числа$",
    re.I,
)
_NO_SOLUTIONS_RE = re.compile(
    r"^(?:нет\s+(?:реш|корн|таких)|no\s+solution|empty\s*set|false)$",
    re.I,
)
_LABELED_PART_RE = re.compile(r"^[абвгдежз]\)\s*", re.I)


def _is_universal_domain(s: str) -> bool:
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    if not s:
        return False
    if s in ("reals", "r", "любое число", "любые числа", "любое значение"):
        return True
    return bool(_UNIVERSAL_DOMAIN_RE.search(s))


def _is_no_solutions_prose(s: str) -> bool:
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    if "нет решений" in s or "нет таких" in s or "решений нет" in s:
        return True
    return bool(_NO_SOLUTIONS_RE.search(s))


def _strip_part_label(s: str) -> str:
    return _LABELED_PART_RE.sub("", (s or "").strip())


def _split_labeled_parts(s: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"[;]", s or ""):
        chunk = _strip_part_label(chunk.strip())
        if chunk:
            parts.append(chunk)
    return parts


def _looks_like_plain_numeric_list(s: str) -> bool:
    """Comma/semicolon separated scalars only — not fractions or algebra."""
    s = _strip_part_label((s or "").strip())
    if not s or _looks_like_algebraic_expression(s):
        return False
    if re.search(r"[a-zA-Z]", s) or "/" in s:
        return False
    parts = [p.strip() for p in re.split(r"[,;]", s) if p.strip()]
    if len(parts) < 2:
        return False
    return all(re.fullmatch(r"-?\d+(?:[.,]\d+)?", p) for p in parts)


def _extract_int_list(s: str) -> Optional[list[int]]:
    s = _strip_part_label(s or "")
    m = re.search(r"Range\((-?\d+),\s*(-?\d+)(?:,\s*(\d+))?\)", s.replace(" ", ""))
    if m:
        start, stop, step = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
        return list(range(start, stop, step))
    if re.search(r"[<>=≠]|!=|Ne\(", s, re.I):
        return None
    # Fractions like 1/3 or 3/1 are not integer lists {1, 3}.
    if "/" in s:
        return None
    # Algebraic expressions like 1/(a-b) must not be parsed as integer lists {1}.
    if _looks_like_algebraic_expression(s):
        return None
    if re.search(r"[a-zA-Z]", s):
        return None
    # Accept both comma and semicolon separated integer lists
    s = re.sub(r"\s*;\s*", ", ", s)
    nums = re.findall(r"-?\d+", s)
    if not nums:
        return None
    try:
        return [int(n) for n in nums]
    except ValueError:
        return None


def _int_lists_equivalent(a: str, b: str) -> bool:
    la, lb = _extract_int_list(a), _extract_int_list(b)
    if la is not None and lb is not None:
        return sorted(la) == sorted(lb)
    return False


def _parse_interval_constraint(s: str) -> Optional[tuple[float, float, bool, bool]]:
    s = re.sub(r"\s+", "", (s or "").lower())
    m = re.match(
        r"^\(?x(?:(>=|>)((?:[-\d./]+)))\)?&\(?(?:x)(?:(<=|<)((?:[-\d./]+)))\)?$",
        s,
        re.I,
    )
    if not m:
        # -6/5 < x < 2  or  (x > -6/5) & (x < 2) already handled above partially
        m2 = re.match(
            r"^([+-]?[\d./]+)(<|<=)([a-zA-Z])(<|<=)([+-]?[\d./]+)$",
            s,
            re.I,
        )
        if m2:
            lo = _to_float_bound(m2.group(1))
            hi = _to_float_bound(m2.group(4))
            if lo is not None and hi is not None:
                return lo, hi, m2.group(2) in ("<", ">"), m2.group(4) in ("<",)
        return None
    lo = _to_float_bound(m.group(2))
    hi = _to_float_bound(m.group(4))
    if lo is None or hi is None:
        return None
    return lo, hi, m.group(1) == ">", m.group(3) == "<"


def _integers_in_constraint(interval: tuple[float, float, bool, bool]) -> list[int]:
    import math

    lo, hi, strict_lo, strict_hi = interval
    if strict_lo:
        start = math.ceil(lo + 1e-12)
    else:
        start = math.ceil(lo - 1e-12)
    if strict_hi:
        end = math.floor(hi - 1e-12)
    else:
        end = math.floor(hi + 1e-12)
    if start > end:
        return []
    return list(range(start, end + 1))


def _integer_set_from_interval(stored: str, candidate: str, question: str) -> bool:
    if "цел" not in (question or "").lower():
        return False
    ints = _extract_int_list(stored)
    interval = _parse_interval_constraint(candidate)
    if ints is None or interval is None:
        return False
    return sorted(ints) == sorted(_integers_in_constraint(interval))


def _parse_ne_exclusions(s: str) -> Optional[set[float]]:
    s = _strip_part_label(s or "")
    text = _normalize_ineq_symbols(s)
    vals: list[float] = []
    for m in re.finditer(r"(?:[a-zA-Z]\s*)?(?:!=|≠|<>)\s*([+-]?[\d.,/]+)", text, re.I):
        v = _to_float_bound(m.group(1))
        if v is not None:
            vals.append(v)
    if vals:
        return set(vals)
    if "continuous_domain" in s:
        cd = _continuous_domain_exclusions(s)
        if cd is not None:
            return cd
    if re.search(r"Ne\(|!=|≠", s, re.I):
        nums = [_to_float_bound(n) for n in re.findall(r"-?\d+(?:\.\d+)?", s)]
        nums = [n for n in nums if n is not None]
        if nums:
            return set(nums)
    if re.fullmatch(r"[\d\s.;,-]+", s):
        nums = [_to_float_bound(n.strip()) for n in re.split(r"[;,]", s) if n.strip()]
        nums = [n for n in nums if n is not None]
        if nums and all(abs(n - round(n)) < 1e-9 for n in nums):
            return set(nums)
    return None


def _continuous_domain_exclusions(s: str) -> Optional[set[float]]:
    """continuous_domain(1/(x - 2), x, Reals) → {2}."""
    m = re.search(r"continuous_domain\(([^,]+)", s, re.I)
    if not m:
        return None
    expr = m.group(1)
    holes: list[float] = []
    for dm in re.finditer(r"/\(\s*([a-zA-Z])\s*-\s*([^)]+)\)", expr):
        v = _to_float_bound(dm.group(2))
        if v is not None:
            holes.append(v)
    for dm in re.finditer(r"/\(\s*([a-zA-Z])\s*\+\s*([^)]+)\)", expr):
        v = _to_float_bound(dm.group(2))
        if v is not None:
            holes.append(-v)
    for dm in re.finditer(r"/([a-zA-Z])\s*-\s*([+-]?[\d./]+)", expr):
        v = _to_float_bound(dm.group(2))
        if v is not None:
            holes.append(v)
    if holes:
        return set(holes)
    return None


def _exclusion_sets_equivalent(a: str, b: str) -> bool:
    ea, eb = _parse_ne_exclusions(a), _parse_ne_exclusions(b)
    if ea is not None and eb is not None:
        return ea == eb
    return False


def _open_example_set_equivalent(a: str, b: str) -> bool:
    low = (a or "").lower()
    if not ("например" in low or "любые" in low or "любое" in low):
        return False
    bound_m = re.search(r"(?:меньше|меньшие|<\s*|младше)\s*(\d+(?:[.,]\d+)?)", low)
    if not bound_m:
        return False
    bound = _to_float_bound(bound_m.group(1))
    ineq = _parse_single_inequality(b)
    if bound is not None and ineq and ineq[1] == "<" and abs(ineq[2] - bound) < 0.02:
        return True
    return False


def _parse_sign_region_prose(s: str) -> Optional[list[tuple[str, str, float]]]:
    regions: list[tuple[str, str, float]] = []
    for m in re.finditer(
        r"(положительн|отрицательн)[а-я]*\s+при\s+([a-zA-Z])\s*(>=|<=|>|<)\s*([+-]?[\d.,/()]+)",
        s or "",
        re.I,
    ):
        sign = "pos" if m.group(1).lower().startswith("полож") else "neg"
        val = _to_float_bound(m.group(4))
        if val is None:
            return None
        regions.append((sign, m.group(3), val))
    return regions if regions else None


def _sign_regions_equivalent(a: str, b: str) -> bool:
    ra, rb = _parse_sign_region_prose(a), _parse_sign_region_prose(b)
    if ra and rb and len(ra) == len(rb):
        ra_s = sorted((r[0], r[1], round(r[2], 4)) for r in ra)
        rb_s = sorted((r[0], r[1], round(r[2], 4)) for r in rb)
        return ra_s == rb_s
    if ra and not rb:
        for sign, op, val in ra:
            probe = f"x {op} {val}".replace(",", ".")
            if not _single_inequalities_equivalent(probe, b):
                return False
        return True
    return False


def _looks_like_algebraic_expression(s: str) -> bool:
    s = (s or "").strip()
    return bool(
        re.search(r"[a-zA-Z]\^|[a-zA-Z]\*\*|\([a-zA-Z]", s)
        or ("/" in s and re.search(r"[a-zA-Z]", s))
    )


def _sets_equivalent(a: str, b: str, question: str = "") -> bool:
    if _is_universal_domain(a) and _is_universal_domain(b):
        return True
    if _is_no_solutions_prose(a) and _is_no_solutions_prose(b):
        return True
    if _exclusion_sets_equivalent(a, b):
        return True
    if _int_lists_equivalent(a, b):
        return True
    if _integer_set_from_interval(a, b, question) or _integer_set_from_interval(b, a, question):
        return True
    if _open_example_set_equivalent(a, b) or _open_example_set_equivalent(b, a):
        return True
    pa, pb = _split_labeled_parts(a), _split_labeled_parts(b)
    if len(pa) >= 2 and len(pa) == len(pb):
        used: set[int] = set()
        for x in pa:
            found = False
            for i, y in enumerate(pb):
                if i in used:
                    continue
                if _sets_equivalent(x, y, question):
                    used.add(i)
                    found = True
                    break
            if not found:
                return False
        return True
    if _looks_like_algebraic_expression(a) and _looks_like_algebraic_expression(b):
        if sympy_equivalent(a, b, "expression") is True:
            return True
    return False


def _is_text_mcq_answer(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return False
    low = s.lower()
    if low in ("да", "нет", "yes", "no", "нет (равно 2)", "неправильно"):
        return True
    if re.fullmatch(r"[абвг]", low):
        return True
    if s.startswith("—") or s.startswith("-"):
        return True
    if re.fullmatch(r"[\d.,()]+", s):
        return True
    return False


def _normalize_mcq_token(s: str) -> str:
    s = _norm(s)
    s = s.replace("pi", "π").replace("\\pi", "π")
    return s


def _mcq_bool_equivalent(a: str, b: str) -> bool:
    """True/False/yes/no ↔ да/нет for MCQ boolean answers."""
    _BOOL_MAP = {
        "true": "да",
        "false": "нет",
        "yes": "да",
        "no": "нет",
        "да": "да",
        "нет": "нет",
        "неправильно": "нет",
        "правильно": "да",
        "нет(равно2)": "нет",
        "верно": "да",
        "неверно": "нет",
        "правда": "да",
        "ложь": "нет",
    }

    def _to_bool_word(s: str) -> str | None:
        raw = (s or "").strip()
        parts = [p.strip() for p in re.split(r"[;,]", raw) if p.strip()]
        if len(parts) >= 2 and all(
            p.lower() in ("true", "false", "yes", "no", "1", "0") for p in parts
        ):
            return "да" if all(p.lower() in ("true", "yes", "1") for p in parts) else "нет"
        key = _norm(raw).replace(" ", "")
        return _BOOL_MAP.get(key, _norm(raw) if key in ("да", "нет") else None)

    na = _to_bool_word(a)
    nb = _to_bool_word(b)
    return na in ("да", "нет") and na == nb


def _mcq_part_equivalent(a: str, b: str) -> bool:
    if _normalize_mcq_token(a) == _normalize_mcq_token(b):
        return True
    if answers_equivalent(a, b, "exact_number"):
        return True
    if answers_equivalent(a, b, "fraction"):
        return True
    return False


def _mcq_answers_equivalent(a: str, b: str) -> bool:
    if _normalize_mcq_token(a) == _normalize_mcq_token(b):
        return True
    pa, pb = _split_compound_parts(a), _split_compound_parts(b)
    if len(pa) >= 2 and len(pa) == len(pb):
        return all(_mcq_part_equivalent(x, y) for x, y in zip(pa, pb))
    if len(pa) >= 2 and len(pb) == 1:
        return _mcq_part_equivalent(pa[0], pb[0])
    return False

def answers_equivalent(
    stored: str,
    candidate: str,
    answer_type: str = "",
    *,
    question: str = "",
) -> bool:
    """Format-tolerant + SymPy equivalence."""
    a = _normalize_pm_text(_normalize_decimal_commas((stored or "").strip()))
    b = _normalize_pm_text(_normalize_decimal_commas((candidate or "").strip()))

    at = (answer_type or "").lower()
    if at in ("fraction", "decimal", "exact_number"):
        if "=" in a:
            a = a.split("=")[-1].strip()
        if "=" in b:
            b = b.split("=")[-1].strip()

    # expression: strip leading LHS assignment like 'S_n = expr' → 'expr'
    # Handles textbook answers that include the formula variable name: "S_n = n/(2n+1)" vs "n/(2n+1)"
    if at == "expression":
        # Match pattern: single variable/subscript = rest (e.g. "S_n = ", "b_6 = ", "a_n = ")
        _lhs_re = re.compile(r"^[a-zA-Z]\w*(?:_\w+)?\s*=\s*", re.I)
        a_stripped = _lhs_re.sub("", a).strip()
        b_stripped = _lhs_re.sub("", b).strip()
        if a_stripped and b_stripped:
            if _norm(a_stripped) == _norm(b_stripped):
                return True
            # keep stripped versions for further comparison below
            a, b = a_stripped, b_stripped

    if not a or not b:
        return False
    if _norm(a) == _norm(b):
        return True

    at = (answer_type or "").lower()
    # Substring match is unsafe for symbolic / multi-root / inequality / fraction answers
    # (e.g. "1/3" is a substring of "-1/3", or "3" of "1/3").
    if at not in (
        "expression",
        "equation_solution",
        "fraction",
        "inequality",
        "set",
        "multiple_choice",
        "exact_number",
        "decimal",
    ):
        if _norm(a) in _norm(b) or _norm(b) in _norm(a):
            return True
    if at == "expression":
        if _parse_labeled_variable_pairs(a) and _parse_labeled_variable_pairs(b):
            if _coordinate_system_equivalent(a, b):
                return True
        na = _normalize_school_expression(a)
        nb = _normalize_school_expression(b)
        if na and nb and _norm(na) == _norm(nb):
            return True
        fa, fb = _fraction_list_parts(a), _fraction_list_parts(b)
        if len(fa) >= 2 and len(fa) == len(fb):
            try:
                from fractions import Fraction

                sa = sorted([float(Fraction(_normalize_school_expression(x))) for x in fa])
                sb = sorted([float(Fraction(_normalize_school_expression(x))) for x in fb])
                if all(abs(x - y) < 1e-4 for x, y in zip(sa, sb)):
                    return True
            except Exception:
                pass
        sa = _parse_scientific_value(a)
        sb = _parse_scientific_value(b)
        if sa is not None and sb is not None and abs(sa - sb) / max(abs(sa), 1e-30) < 0.02:
            return True

    if at == "fraction":
        na = _normalize_school_expression(a)
        nb = _normalize_school_expression(b)
        if na and nb and _norm(na) == _norm(nb):
            return True
        val_a = _try_fraction(a)
        val_b = _try_fraction(b)
        def _extract_tuple_nums(s: str) -> list[float]:
            s_clean = s.strip().replace("(", "").replace(")", "").replace("[", "").replace("]", "")
            parts = s_clean.split(";") if ";" in s_clean else s_clean.split(",")
            res = []
            for p in parts:
                try:
                    res.append(float(p.strip().replace(",", ".")))
                except ValueError:
                    pass
            return res
        if val_a is not None:
            nums_b = _extract_tuple_nums(b)
            if len(nums_b) == 2 and nums_b[1] != 0:
                if abs(val_a - nums_b[0]/nums_b[1]) < 1e-6:
                    return True
        if val_b is not None:
            nums_a = _extract_tuple_nums(a)
            if len(nums_a) == 2 and nums_a[1] != 0:
                if abs(val_b - nums_a[0]/nums_a[1]) < 1e-6:
                    return True
        fa, fb = _fraction_list_parts(a), _fraction_list_parts(b)
        if len(fa) >= 2 and len(fa) == len(fb):
            try:
                from fractions import Fraction

                sa = sorted([float(Fraction(_normalize_school_expression(x))) for x in fa])
                sb = sorted([float(Fraction(_normalize_school_expression(x))) for x in fb])
                if all(abs(x - y) < 1e-4 for x, y in zip(sa, sb)):
                    return True
            except Exception:
                pass

    if at == "equation_solution":
        if _mcq_bool_equivalent(a, b):
            return True
        if _compound_parts_equivalent(a, b):
            return True
        if _coordinate_system_equivalent(a, b):
            return True
        if _equation_solution_sets_equivalent(a, b):
            return True
        va = _bare_pm_value_set(a)
        vb = _bare_pm_value_set(b)
        if va and vb and len(va) == len(vb):
            if all(abs(x - y) < 1e-2 for x, y in zip(va, vb)):
                return True
        # Handle 'x=5; y=3' vs '(5; 3)' — semicolon-separated variable assignments vs coord tuples
        def _all_pairs(s: str) -> list:
            return (
                _parse_coordinate_pairs(s)
                or _parse_semicolon_xy_pairs(s)
                or _parse_labeled_variable_pairs(s)
                or _parse_indexed_variable_pairs(s)
            )
        sa_pairs = _all_pairs(a)
        sb_pairs = _all_pairs(b)
        if sa_pairs and sb_pairs and len(sa_pairs) == len(sb_pairs):
            if sorted(sa_pairs) == sorted(sb_pairs):
                return True
        # If both sides contain same set of numbers (prose answers like "мастер 60; ученик 40")
        # Only apply when both have words (text-rich answers), not pure math
        has_words_a = bool(re.search(r"[а-яёА-ЯЁa-zA-Z]{3,}", a))
        has_words_b = bool(re.search(r"[а-яёА-ЯЁa-zA-Z]{3,}", b))
        if has_words_a and has_words_b:
            nums_a = _extract_numbers_sorted(a)
            nums_b = _extract_numbers_sorted(b)
            if nums_a and nums_b and len(nums_a) == len(nums_b) and len(nums_a) >= 2:
                if all(abs(x - y) < 0.1 for x, y in zip(nums_a, nums_b)):
                    return True

    if at == "coordinate":
        if _coordinate_system_equivalent(a, b):
            return True
        if _parse_labeled_variable_pairs(a) and _parse_labeled_variable_pairs(b):
            if _coordinate_system_equivalent(a, b):
                return True
        # LLM may return x = a, y = b for coordinate pairs
        if answers_equivalent(a, b, "equation_solution"):
            return True

    if at == "inequality":
        if _inequalities_equivalent(a, b):
            return True
        if _is_universal_domain(a) and _is_universal_domain(b):
            return True
        if _is_no_solutions_prose(a) and _is_no_solutions_prose(b):
            return True
        if _sign_regions_equivalent(a, b) or _sign_regions_equivalent(b, a):
            return True
        # SymPy-based set comparison: handles (a; b) ∪ (c; d) ↔ x < b или x > c
        try:
            _iv_eq = _intervals_equivalent(a, b)
            if _iv_eq is True:
                return True
        except Exception:
            pass

    if at == "set":
        if _sets_equivalent(a, b, question=question):
            return True

    if at == "multiple_choice":
        if _mcq_bool_equivalent(a, b):
            return True
        if _mcq_answers_equivalent(a, b):
            return True

    if at in ("exact_number", "decimal", "fraction"):
        if _numeric_parts_equivalent(a, b):
            return True
        sa = _to_float_bound(a) if at != "fraction" else _try_fraction(a)
        sb = _to_float_bound(b) if at != "fraction" else _try_fraction(b)
        if sa is not None and sb is not None:
            denom = max(abs(sa), abs(sb), 1.0)
            if abs(sa - sb) / denom < 0.02:
                return True

    fa, fb = _try_fraction(a), _try_fraction(b)
    if fa is not None and fb is not None and abs(fa - fb) < 1e-6:
        return True

    if not (_has_free_parameters(a) or _has_free_parameters(b)):
        # Same numeric multiset must not collapse distinct comparisons (e.g. -√14 > … vs < …).
        rel_re = re.compile(r"[<>≤≥=]|\\geqslant|\\leqslant", re.I)
        has_rel = bool(rel_re.search(a) or rel_re.search(b))
        if not has_rel:
            if _looks_like_plain_numeric_list(a) and _looks_like_plain_numeric_list(b):
                na, nb = sorted(_extract_numbers(a)), sorted(_extract_numbers(b))
                if na and nb and len(na) == len(nb) and all(
                    abs(x - y) < 1e-4 for x, y in zip(na, nb)
                ):
                    return True
                if na and nb and set(round(x, 4) for x in na) == set(
                    round(x, 4) for x in nb
                ):
                    return True

    sym = sympy_equivalent(a, b, answer_type)
    if sym is True:
        return True
    # algebraic rewrite: 2n+1 vs n+(n+1)
    if re.search(r"\bn\b", a, re.I) and re.search(r"\bn\b", b, re.I):
        mc = monte_carlo_equivalent(a.replace("n", "x"), b.replace("n", "x"))
        if mc is True:
            return True

    return False


def _gemini_solve(question: str, answer_type: str, *, use_pro: bool = False) -> str:
    from src.pipeline.deepseek_client import (
        call_deepseek,
        get_deepseek_model,
        parse_json_response,
    )

    model = get_deepseek_model() if use_pro else get_deepseek_model()
    label = "Pro" if use_pro else "Flash"
    prompt = (
        f"Ты — математический педагог. Реши задачу ({label}) и верни только финальный ответ.\n\n"
        f"Текст: {question}\n"
        f"Тип ответа: {answer_type}\n\n"
        'Верни JSON: {"answer":"<окончательный ответ>"}\n'
        "answer — краткий точный ответ в привычной школьной записи. Только JSON."
    )
    raw = call_deepseek(
        prompt,
        model=model,
        temperature=0.1,
        max_tokens=2048,
    )
    data = parse_json_response(raw)
    if isinstance(data, dict):
        ans = data.get("answer", "")
        if isinstance(ans, (int, float)):
            return str(ans)
        return str(ans).strip()
    return ""


def gemini_solve(question: str, answer_type: str) -> str:
    return _gemini_solve(question, answer_type, use_pro=False)


def gemini_solve_pro(question: str, answer_type: str) -> str:
    return _gemini_solve(question, answer_type, use_pro=True)


def should_skip_verify(question: str, answer_type: str) -> Optional[str]:
    q = (question or "").strip()
    if _SKIP_VERIFY_RE.search(q[:200]):
        return "proof_or_drawing"
    if answer_type == "text" and len(q) > 300:
        return "long_text"
    if answer_type in ("coordinate", "open_text"):
        return f"type_{answer_type}"
    if _INCOMPLETE_Q_RE.match(q) or (len(q) < 25 and not re.search(r"[0-9=+\-*/^()\\$]", q)):
        return "incomplete_question"
    return None


def _dual_consensus(a: str, b: str, answer_type: str) -> bool:
    if answers_equivalent(a, b, answer_type):
        return True
    sym = sympy_equivalent(a, b, answer_type)
    return sym is True


def _decide_correction(
    question: str,
    stored: str,
    consensus: str,
    answer_type: str,
) -> AnswerVerifyResult:
    """Flash+Pro agree on consensus ≠ stored — SymPy gate before any change."""
    base_tags = {
        "answer_gemini_candidate": consensus[:500],
        "answer_gemini_flash": consensus[:500],
    }

    sym_stored_cons = sympy_equivalent(stored, consensus, answer_type)
    if sym_stored_cons is True:
        return AnswerVerifyResult(
            match=True,
            gemini_answer=consensus,
            stored_answer=stored,
            final_answer=stored,
            verified=True,
            tags_patch={
                **base_tags,
                "answer_gemini_verified": True,
                "answer_verify_mode": "sympy_match",
            },
        )

    stored_ok = try_validate_answer_for_question(question, stored, answer_type)
    consensus_ok = try_validate_answer_for_question(question, consensus, answer_type)

    # Strategy 2: back-substitute roots into equation extracted from question text.
    # This catches cases where Strategy 1 (expression simplification) can't verify,
    # but we CAN algebraically prove which answer is correct.
    if stored_ok is None:
        stored_ok = back_substitute_roots(question, stored, answer_type)
    if consensus_ok is None:
        consensus_ok = back_substitute_roots(question, consensus, answer_type)

    if stored_ok is True and consensus_ok is not True:
        log.info(
            "Verify conflict — keep stored [%s]: stored=%r consensus=%r",
            answer_type, stored[:50], consensus[:50],
        )
        return AnswerVerifyResult(
            match=False,
            gemini_answer=consensus,
            stored_answer=stored,
            final_answer=stored,
            verified=True,
            skip_distractors=True,
            skip_reason="verify_conflict",
            tags_patch={
                **base_tags,
                "answer_gemini_verified": True,
                "verify_conflict": True,
                "answer_verify_mode": "conflict",
            },
        )

    if consensus_ok is True and stored_ok is not True:
        log.info(
            "SymPy-confirmed correction [%s]: stored=%r → consensus=%r",
            answer_type, stored[:50], consensus[:50],
        )
        return AnswerVerifyResult(
            match=False,
            gemini_answer=consensus,
            stored_answer=stored,
            final_answer=consensus,
            corrected=True,
            verified=True,
            tags_patch={
                **base_tags,
                "answer_gemini_verified": True,
                "answer_corrected_by_gemini": True,
                "answer_corrected_sympy_confirmed": True,
                "answer_previous": stored[:500],
                "answer_verify_mode": "corrected_sympy",
            },
        )

    log.warning(
        "Verify unresolved — no SymPy confirmation [%s]: stored=%r consensus=%r "
        "stored_ok=%s consensus_ok=%s sym_equiv=%s",
        answer_type, stored[:50], consensus[:50], stored_ok, consensus_ok, sym_stored_cons,
    )
    return AnswerVerifyResult(
        match=False,
        gemini_answer=consensus,
        stored_answer=stored,
        final_answer=stored,
        skip_distractors=True,
        skip_reason="verify_unresolved",
        tags_patch={
            **base_tags,
            "answer_gemini_verified": False,
            "verify_unresolved": True,
            "answer_verify_mode": "unresolved",
        },
    )


def verify_answer(
    question: str,
    stored_answer: str,
    answer_type: str,
    *,
    auto_fix: bool = True,
    call_deepseek: bool = True,
    dual_consensus: bool = True,
) -> AnswerVerifyResult:
    """Re-solve with Gemini (+ Pro on mismatch), SymPy gate before any correction."""
    stored = (stored_answer or "").strip()
    if not stored or stored in ("—", "-", "?"):
        return AnswerVerifyResult(
            match=False,
            stored_answer=stored,
            final_answer=stored,
            skip_distractors=True,
            skip_reason="empty_answer",
        )

    skip = should_skip_verify(question, answer_type or "")
    if skip:
        return AnswerVerifyResult(
            match=True,
            stored_answer=stored,
            final_answer=stored,
            verified=True,
            skip_reason=skip,
            tags_patch={"answer_gemini_verified": True, "answer_verify_mode": "skipped"},
        )

    at = (answer_type or "").lower()
    if at not in _VERIFIABLE_TYPES:
        return AnswerVerifyResult(
            match=True,
            stored_answer=stored,
            final_answer=stored,
            verified=True,
            skip_reason=f"type_{at}",
            tags_patch={"answer_gemini_verified": True, "answer_verify_mode": "skipped_type"},
        )

    gemini_flash = ""
    gemini_pro = ""
    if call_deepseek:
        try:
            gemini_flash = gemini_solve(question, at)
        except Exception as exc:
            log.warning("Gemini Flash verify failed: %s", exc)
            return AnswerVerifyResult(
                match=False,
                stored_answer=stored,
                final_answer=stored,
                skip_distractors=False,
                skip_reason="gemini_error",
                tags_patch={"answer_verify_error": str(exc)[:200]},
            )

    if not gemini_flash:
        return AnswerVerifyResult(
            match=False,
            stored_answer=stored,
            final_answer=stored,
            skip_distractors=False,
            skip_reason="gemini_empty",
        )

    if answers_equivalent(stored, gemini_flash, at):
        stored_ok = try_validate_answer_for_question(question, stored, at)
        if stored_ok is False:
            log.warning(
                "Verify unresolved — stored fails SymPy check [%s]: %r flash=%r",
                at, stored[:50], gemini_flash[:50],
            )
            return AnswerVerifyResult(
                match=False,
                gemini_answer=gemini_flash,
                stored_answer=stored,
                final_answer=stored,
                skip_distractors=True,
                skip_reason="stored_sympy_invalid",
                tags_patch={
                    "answer_gemini_verified": False,
                    "verify_unresolved": True,
                    "answer_gemini_candidate": gemini_flash[:500],
                    "answer_verify_mode": "stored_invalid",
                },
            )
        return AnswerVerifyResult(
            match=True,
            gemini_answer=gemini_flash,
            stored_answer=stored,
            final_answer=stored,
            verified=True,
            tags_patch={
                "answer_gemini_verified": True,
                "answer_verify_mode": "match",
            },
        )

    if not auto_fix:
        return AnswerVerifyResult(
            match=False,
            gemini_answer=gemini_flash,
            stored_answer=stored,
            final_answer=stored,
            skip_distractors=True,
            skip_reason="mismatch_no_autofix",
            tags_patch={
                "answer_gemini_verified": False,
                "answer_mismatch": True,
                "answer_gemini_candidate": gemini_flash[:500],
                "answer_verify_mode": "mismatch",
            },
        )

    consensus = gemini_flash
    if dual_consensus:
        try:
            gemini_pro = gemini_solve_pro(question, at)
        except Exception as exc:
            log.warning("Gemini Pro verify failed: %s", exc)
            gemini_pro = ""

        if gemini_pro and _dual_consensus(gemini_flash, gemini_pro, at):
            consensus = gemini_pro if len(gemini_pro) >= len(gemini_flash) else gemini_flash
        else:
            log.warning(
                "Dual consensus failed [%s]: flash=%r pro=%r",
                at, gemini_flash[:40], (gemini_pro or "")[:40],
            )
            return AnswerVerifyResult(
                match=False,
                gemini_answer=gemini_flash,
                gemini_answer_pro=gemini_pro,
                stored_answer=stored,
                final_answer=stored,
                skip_distractors=True,
                skip_reason="dual_consensus_failed",
                tags_patch={
                    "answer_gemini_verified": False,
                    "verify_unresolved": True,
                    "answer_gemini_candidate": gemini_flash[:500],
                    "answer_gemini_pro_candidate": (gemini_pro or "")[:500],
                    "answer_verify_mode": "dual_failed",
                },
            )

    result = _decide_correction(question, stored, consensus, at)
    result.gemini_answer = gemini_flash
    result.gemini_answer_pro = gemini_pro
    return result


def apply_verify_to_task(task, result: AnswerVerifyResult) -> None:
    """Mutate ExtractedTask: answer_raw + tags from verify result."""
    task.answer_raw = result.final_answer
    if not task.tags:
        task.tags = {}
    task.tags.update(result.tags_patch)
    # Stale flags cleared on next persist via verify_distractor_pass
