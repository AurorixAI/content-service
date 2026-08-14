"""
Interval and inequality normalizer for Smart Verify.

Converts between different representations of the same mathematical set:
  - Interval notation: (-∞; -2) ∪ (2/3; +∞)
  - Inequality text:   x < -2 или x > 2/3
  - SymPy sets:        Union(Interval.open(-oo, -2), Interval.open(Rational(2,3), oo))

All public functions return True/False/None (None = cannot decide).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

_COMMA_DECIMAL = re.compile(r"(?<!\d),(?=\d)|(?<=\d),(?!\d)")  # Russian decimal comma

def _prep(s: str) -> str:
    """Normalize display LaTeX and school notation before set parsing.

    Stored answers may be wrapped in LaTeX while model evidence commonly uses
    plain school notation.  This function intentionally changes notation only
    (never a bound or an operator), so equivalent intervals reach the same
    mathematical comparator.
    """
    s = (s or "").strip()
    s = s.replace("$", "")
    s = re.sub(r"\\(?:left|right|bigl|bigr|Bigl|Bigr|big|Big)", "", s)
    s = s.replace(r"\dfrac", r"\frac")
    # Interval endpoints use scalar fractions. Repeat for a simple nested
    # LaTeX fraction without attempting to parse arbitrary LaTeX expressions.
    for _ in range(2):
        normalized = re.sub(
            r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", s,
        )
        if normalized == s:
            break
        s = normalized
    s = (
        s.replace(r"\infty", "∞")
        .replace(r"\cup", "∪")
        .replace(r"\cap", "∩")
        .replace(r"\in", "∈")
        .replace(r"\leqslant", "≤")
        .replace(r"\leq", "≤")
        .replace(r"\geqslant", "≥")
        .replace(r"\geq", "≥")
        .replace(r"\wedge", " and ")
        .replace(r"\land", " and ")
        .replace(r"\vee", " or ")
        .replace(r"\lor", " or ")
        .replace("&", " and ")
        .replace(r"\,", " ")
        .replace(r"\;", " ")
    )
    # Endpoint fractions are mathematical atoms: model code frequently emits
    # spaces around `/` and after a unary minus, while the set parser expects
    # a single scalar token (e.g. ``-7/4``).
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"-\s+(?=\d)", "-", s)
    # Replace minus/dash variants
    s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    # Infinity variants — order matters (longer first)
    s = s.replace("+\u221e", "oo").replace("-\u221e", "-oo").replace("\u221e", "oo")
    s = s.replace("+inf", "oo").replace("-inf", "-oo")
    s = _COMMA_DECIMAL.sub(".", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _strip_outer_parens(s: str) -> str:
    """Remove balanced outer parentheses around one logical clause only."""
    value = (s or "").strip()
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        encloses_all = True
        for index, char in enumerate(value):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(value) - 1:
                    encloses_all = False
                    break
        if depth != 0 or not encloses_all:
            break
        value = value[1:-1].strip()
    return value


def _split_top_level_logic(s: str) -> tuple[list[str], list[str]]:
    """Split ``and``/``or`` outside brackets and preserve their semantics."""
    value = _strip_outer_parens(s)
    parts: list[str] = []
    operators: list[str] = []
    start = 0
    depth = 0
    index = 0
    while index < len(value):
        char = value[index]
        if char in "([":
            depth += 1
            index += 1
            continue
        if char in ")]":
            depth = max(0, depth - 1)
            index += 1
            continue
        if depth == 0:
            word = re.match(r"\s+(или|or|и|and)\s+", value[index:], re.I)
            if word:
                parts.append(value[start:index].strip())
                operators.append(
                    "union" if word.group(1).lower() in {"или", "or"} else "intersection"
                )
                index += word.end()
                start = index
                continue
        index += 1
    if operators:
        parts.append(value[start:].strip())
        return parts, operators
    return [value], []


def _parse_bound(s: str):
    """Parse a boundary value string to SymPy number or oo/-oo."""
    try:
        from sympy import oo, Rational
        s = s.strip()
        if s in ("oo", "+oo"):
            return oo
        if s == "-oo":
            return -oo
        # fraction: 2/3, -1/4
        m = re.match(r"^(-?\d+)/(\d+)$", s)
        if m:
            return Rational(int(m.group(1)), int(m.group(2)))
        # mixed: 2 1/3
        m = re.match(r"^(-?\d+)\s+(\d+)/(\d+)$", s)
        if m:
            whole = int(m.group(1))
            frac = Rational(int(m.group(2)), int(m.group(3)))
            return whole + frac if whole >= 0 else whole - frac
        # LaTeX frac: \frac{1}{2}
        m = re.search(r"\\frac\{(-?\d+)\}\{(\d+)\}", s)
        if m:
            return Rational(int(m.group(1)), int(m.group(2)))
        # plain number (int or decimal)
        return Rational(s).limit_denominator(10000) if "." in s else Rational(int(s))
    except Exception:
        try:
            from sympy import sympify
            return sympify(s)
        except Exception:
            return None


# ── interval notation parser: (a; b) ∪ [c; d] ────────────────────────────────

_INTERVAL_RE = re.compile(
    r"([(\[])\s*"           # opening bracket
    r"(-?oo|[^;,\[\]()∪∩]+?)"   # lower bound
    r"\s*[;,]\s*"           # separator
    r"(-?oo|[^;,\[\]()∪∩]+?)"   # upper bound
    r"\s*([)\]])",          # closing bracket
    re.I,
)


def _parse_one_interval(bracket_open: str, lo_s: str, hi_s: str, bracket_close: str):
    """Parse one interval like (a; b] → SymPy Interval."""
    try:
        from sympy import Interval
        lo = _parse_bound(lo_s.strip())
        hi = _parse_bound(hi_s.strip())
        if lo is None or hi is None:
            return None
        left_open = bracket_open == "("
        right_open = bracket_close == ")"
        return Interval(lo, hi, left_open=left_open, right_open=right_open)
    except Exception:
        return None


def _parse_interval_notation(s: str):
    """
    Parse full interval notation expression, possibly joined with ∪.
    Returns SymPy set or None.
    """
    s = _prep(s)
    # Split on ∪ or ASCII U (used as union) or \cup
    parts_raw = re.split(r"[∪∩]|(?<!\w)\bU\b(?!\w)|\\cup|\\cap", s, flags=re.I)
    if len(parts_raw) == 1 and not _INTERVAL_RE.search(s):
        return None

    intervals = []
    for part in parts_raw:
        m = _INTERVAL_RE.search(part)
        if m:
            iv = _parse_one_interval(m.group(1), m.group(2), m.group(3), m.group(4))
            if iv is not None:
                intervals.append(iv)
            else:
                return None
        elif part.strip():
            return None  # unrecognized fragment

    if not intervals:
        return None
    if len(intervals) == 1:
        return intervals[0]
    try:
        from sympy import Union
        return Union(*intervals)
    except Exception:
        return None


# ── inequality text parser: x < a или x > b ───────────────────────────────────

_INEQ_VAR_RE = re.compile(
    r"([a-zA-Zа-яА-Я])\s*(<=|>=|<|>|≤|≥|⩽|⩾)\s*([^\s,;∪∩]+)"
)
_VAR_INEQ_RE = re.compile(
    r"([^\s,;∪∩]+)\s*(<=|>=|<|>|≤|≥|⩽|⩾)\s*([a-zA-Zа-яА-Я])"
)

_OP_MAP = {"<=": "<=", ">=": ">=", "<": "<", ">": ">",
           "≤": "<=", "≥": ">=", "⩽": "<=", "⩾": ">="}


def _ineq_to_sympy_set(var, op: str, bound_s: str, flipped: bool = False):
    """var op bound → SymPy Interval."""
    try:
        from sympy import Interval, oo
        bound = _parse_bound(bound_s.strip())
        if bound is None:
            return None
        if flipped:
            # bound op var → flip: var flip(op) bound
            op = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}[op]
        if op == "<":
            return Interval(-oo, bound, left_open=True, right_open=True)
        if op == "<=":
            return Interval(-oo, bound, left_open=True, right_open=False)
        if op == ">":
            return Interval(bound, oo, left_open=True, right_open=True)
        if op == ">=":
            return Interval(bound, oo, left_open=False, right_open=True)
    except Exception:
        pass
    return None


def _parse_inequality_text(s: str):
    """
    Parse inequality text like 'x < -2 или x > 2/3' → SymPy set.
    Also handles: x ∈ (-∞; 3) ∪ (3; +∞) embedded notation.
    """
    s = _prep(s)

    # Remove "x ∈" prefix if present
    s = re.sub(r"^[a-zA-Zа-яА-Я]\s*[∈]\s*", "", s)

    # If it looks like interval notation already, hand off
    if _INTERVAL_RE.search(s):
        return _parse_interval_notation(s)

    clauses, operators = _split_top_level_logic(s)
    if not clauses or any(not clause for clause in clauses):
        return None

    sets = []
    for clause in clauses:
        clause = _strip_outer_parens(clause)
        m = _INEQ_VAR_RE.match(clause)
        if m:
            iv = _ineq_to_sympy_set(m.group(1), _OP_MAP.get(m.group(2), m.group(2)), m.group(3))
            if iv is None:
                return None
            sets.append(iv)
            continue
        m = _VAR_INEQ_RE.match(clause)
        if m:
            iv = _ineq_to_sympy_set(m.group(3), _OP_MAP.get(m.group(2), m.group(2)), m.group(1), flipped=True)
            if iv is None:
                return None
            sets.append(iv)
            continue
        # Maybe it's a single bound like "> 5" (no variable)
        m2 = re.match(r"^(<=|>=|<|>|≤|≥)\s*(.+)$", clause)
        if m2:
            iv = _ineq_to_sympy_set("x", _OP_MAP.get(m2.group(1), m2.group(1)), m2.group(2))
            if iv is None:
                return None
            sets.append(iv)
            continue
        return None  # unrecognized clause

    if not sets:
        return None
    if len(sets) == 1:
        return sets[0]
    try:
        from sympy import Intersection, Union

        result = sets[0]
        for operator, item in zip(operators, sets[1:]):
            result = Union(result, item) if operator == "union" else Intersection(result, item)
        return result
    except Exception:
        return None


# ── double-sided inequality: a < x <= b ──────────────────────────────────────

_DOUBLE_INEQ_RE = re.compile(
    r"(-?[^\s<>=≤≥]+)\s*(<=|<|≤)\s*([a-zA-Zа-яА-Я])\s*(<=|<|≤|>=|>|≥)\s*(-?[^\s<>=≤≥]+)"
)


def _parse_double_inequality(s: str):
    """Handle 'a < x <= b' style expressions."""
    s = _prep(s)
    m = _DOUBLE_INEQ_RE.match(s.strip())
    if not m:
        return None
    try:
        from sympy import Interval
        lo = _parse_bound(m.group(1))
        hi = _parse_bound(m.group(5))
        if lo is None or hi is None:
            return None
        left_open = m.group(2) in ("<", "≤") and m.group(2) != "<="  # strict
        left_open = m.group(2) == "<"
        right_open = m.group(4) == "<"
        return Interval(lo, hi, left_open=left_open, right_open=right_open)
    except Exception:
        return None


# ── "no solutions" / "all reals" detection ───────────────────────────────────

_NO_SOL_PATTERNS = re.compile(
    r"нет\s*(?:решений?|корней?)|no\s+solutions?|∅|пустое\s+множество|empty", re.I
)
_ALL_REALS_PATTERNS = re.compile(
    r"(?:все|any)\s+(?:действ|вещ|real)|вся\s+числовая\s+прямая|(-?oo\s*[;,]\s*[+]?oo)|"
    r"R\b|\(-oo\s*[;,]\s*oo\)", re.I
)


def _is_no_solutions(s: str) -> bool:
    return bool(_NO_SOL_PATTERNS.search(s))


def _is_all_reals(s: str) -> bool:
    return bool(_ALL_REALS_PATTERNS.search(_prep(s)))


# ── main comparison ───────────────────────────────────────────────────────────

def _to_sympy_set(s: str):
    """
    Try all parsers in order. Returns SymPy set or None.
    Order: double-inequality → interval notation → inequality text.
    """
    s = _prep(s)
    result = _parse_double_inequality(s)
    if result is not None:
        return result
    result = _parse_interval_notation(s)
    if result is not None:
        return result
    result = _parse_inequality_text(s)
    return result


def _sympy_sets_equal(sa, sb) -> Optional[bool]:
    """Compare two SymPy sets for equality."""
    try:
        from sympy import EmptySet
        if sa == sb:
            return True
        diff = sa.symmetric_difference(sb)
        if diff == EmptySet:
            return True
        return False
    except Exception:
        try:
            return sa == sb
        except Exception:
            return None


def _monte_carlo_interval(sa, sb, trials: int = 6) -> Optional[bool]:
    """
    Numeric sampling: pick test points, check if both sets agree.
    Returns True if equivalent, False if not, None if can't test.
    """
    try:
        import random
        from sympy import Rational, oo

        # Collect a range to sample from
        sample_points = [
            Rational(-10), Rational(-3), Rational(-1), Rational(0),
            Rational(1), Rational(3), Rational(10), Rational(1, 2),
            Rational(-1, 2), Rational(7, 3), Rational(-7, 3),
        ]
        rng = random.Random(42)
        extra = [Rational(rng.randint(-20, 20)) for _ in range(trials)]
        sample_points.extend(extra)

        for pt in sample_points:
            try:
                in_a = sa.contains(pt)
                in_b = sb.contains(pt)
                if in_a != in_b:
                    return False
            except Exception:
                continue
        return True
    except Exception:
        return None


def intervals_equivalent(a: str, b: str) -> Optional[bool]:
    """
    Public API: compare two inequality/interval expressions mathematically.

    Returns:
        True  — mathematically the same set
        False — demonstrably different sets
        None  — cannot determine (both parsers failed, or ambiguous)
    """
    if not a or not b:
        return None
    if _prep(a) == _prep(b):
        return True

    # Quick prose checks
    a_no_sol = _is_no_solutions(a)
    b_no_sol = _is_no_solutions(b)
    if a_no_sol and b_no_sol:
        return True
    if a_no_sol != b_no_sol:
        return False

    a_all = _is_all_reals(a)
    b_all = _is_all_reals(b)
    if a_all and b_all:
        return True
    if a_all != b_all:
        return False

    sa = _to_sympy_set(a)
    sb = _to_sympy_set(b)

    if sa is None or sb is None:
        return None  # Cannot parse → we don't know

    # Symbolic equality first
    exact = _sympy_sets_equal(sa, sb)
    if exact is not None:
        return exact

    # Monte-Carlo fallback
    return _monte_carlo_interval(sa, sb)


def normalize_to_interval_notation(s: str) -> Optional[str]:
    """
    Convert any inequality expression to canonical interval notation.
    E.g. 'x < -2 или x > 2/3' → '(-∞; -2) ∪ (2/3; +∞)'
    Returns None if cannot parse.
    """
    sympy_set = _to_sympy_set(s)
    if sympy_set is None:
        return None
    try:
        from sympy import Interval, Union, oo
        return _sympy_set_to_notation(sympy_set)
    except Exception:
        return None


def _sympy_set_to_notation(s) -> str:
    """Convert SymPy set to human-readable interval notation."""
    try:
        from sympy import Union, Interval, oo, EmptySet
        if s == EmptySet:
            return "∅"
        if isinstance(s, Interval):
            lo = "-∞" if s.start == -oo else _fmt_bound(s.start)
            hi = "+∞" if s.end == oo else _fmt_bound(s.end)
            lb = "(" if s.left_open else "["
            rb = ")" if s.right_open else "]"
            return f"{lb}{lo}; {hi}{rb}"
        if isinstance(s, Union):
            parts = sorted(s.args, key=lambda iv: float(iv.start) if hasattr(iv, 'start') else 0)
            return " ∪ ".join(_sympy_set_to_notation(p) for p in parts)
    except Exception:
        pass
    return str(s)


def _fmt_bound(val) -> str:
    """Format a SymPy bound value to a human-readable string."""
    try:
        from sympy import Rational
        if isinstance(val, Rational):
            if val.q == 1:
                return str(val.p)
            return f"{val.p}/{val.q}"
        f = float(val)
        if abs(f - round(f)) < 1e-9:
            return str(int(round(f)))
        return str(round(f, 4)).rstrip("0").rstrip(".")
    except Exception:
        return str(val)
