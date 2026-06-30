"""Local SymPy gate for Smart Verify (evaluate LLM sympy_compatible_string)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from src.pipeline.answer_sympy import _latexish_to_sympy, parse_expr, split_answer_parts, sympy_equivalent

log = logging.getLogger(__name__)

# Answer types supported by Smart Verify compute step
SMART_VERIFY_TYPES = frozenset({
    "exact_number",
    "decimal",
    "fraction",
    "expression",
    "equation_solution",
    "inequality",
    "set",
    "multiple_choice",
})

CANONICAL_REASONS = frozenset({"sympy_match", "string_match"})


def _sympy_namespace() -> dict[str, Any]:
    import sympy
    from sympy import (
        Abs,
        And,
        E,
        Eq,
        Ge,
        Gt,
        Interval,
        Le,
        Lt,
        Ne,
        Or,
        Piecewise,
        Union,
        oo,
        pi,
        simplify,
        solve,
        sqrt,
        symbols,
    )

    x, y, z, n, a, b, c, t = symbols("x y z n a b c t", real=True)
    return {
        "Abs": Abs,
        "Piecewise": Piecewise,
        "Interval": Interval,
        "Union": Union,
        "And": And,
        "Or": Or,
        "oo": oo,
        "Eq": Eq,
        "Ne": Ne,
        "Le": Le,
        "Ge": Ge,
        "Lt": Lt,
        "Gt": Gt,
        "solve": solve,
        "symbols": symbols,
        "Symbol": symbols,
        "simplify": simplify,
        "sqrt": sqrt,
        "pi": pi,
        "E": E,
        "x": x,
        "y": y,
        "z": z,
        "n": n,
        "a": a,
        "b": b,
        "c": c,
        "t": t,
        "sympy": sympy,
    }


def _equation_parse_locals() -> dict[str, Any]:
    """local_dict for parse_expr when reading equations from question text."""
    import sympy
    from sympy import Abs, Eq, symbols

    x = symbols("x", real=True)
    return {"x": x, "Abs": Abs, "Eq": Eq, "symbols": symbols}


def _absify_pipes(s: str) -> str:
    """Convert |expr| to Abs(expr) for school-style modulus notation."""
    raw = (s or "").strip()
    if "|" not in raw:
        return raw
    # Simple balanced |...| replacement (innermost first)
    while "|" in raw:
        m = re.search(r"\|([^|]+)\|", raw)
        if not m:
            break
        inner = m.group(1).strip()
        raw = raw[: m.start()] + f"Abs({inner})" + raw[m.end() :]
    return raw


_PROSE_ANSWERS_RE = re.compile(
    r"^(нет\s*корн|нет\s*реш|no\s*real|no\s*solution|empty\s*set|"
    r"люб(?:ое|ые)\s+числ|нет\s+таких|решений\s+нет)$",
    re.I,
)
_WRITE_EQUATION_RE = re.compile(
    r"(запишите|записать|представьте|запиши).{0,40}уравнен",
    re.I,
)


def is_write_equation_task(question: str) -> bool:
    """Task asks to write an equation, not solve for x."""
    return bool(_WRITE_EQUATION_RE.search(question or ""))


def is_prose_answer(s: str) -> bool:
    s = (s or "").strip().lower()
    if bool(_PROSE_ANSWERS_RE.search(s)):
        return True
    if "нет корней" in s or "нет решений" in s or "нет таких" in s:
        return True
    if re.search(r"^люб(?:ое|ые)\s+числ", s):
        return True
    if re.search(r"любые\s+два\s+числ", s):
        return True
    return False


def _is_text_mcq_answer(s: str) -> bool:
    from src.pipeline.answer_verify import _is_text_mcq_answer as _mcq

    return _mcq(s)


def format_equation_from_eq(eq: Any) -> str:
    """Normalize Eq(lhs,rhs) to school equation string."""
    import sympy

    try:
        lhs = sympy.expand(eq.lhs)
        rhs = sympy.expand(eq.rhs)
        return f"{lhs} = {rhs}"
    except Exception:
        return str(eq).replace("**", "^")


def equation_form_equivalent(a: str, b: str) -> bool:
    """True if two equations describe the same relation (expanded lhs-rhs)."""
    import sympy

    def residual(s: str) -> Any:
        s = (s or "").strip()
        if "=" not in s:
            return None
        lhs_s, rhs_s = s.split("=", 1)
        lhs = parse_expr(_latexish_to_sympy(lhs_s.strip()))
        rhs = parse_expr(_latexish_to_sympy(rhs_s.strip()))
        if lhs is None or rhs is None:
            return None
        return sympy.expand(lhs - rhs)

    ra, rb = residual(a), residual(b)
    if ra is None or rb is None:
        return False
    try:
        return sympy.simplify(ra - rb) == 0
    except Exception:
        return False


def format_school_notation(value: str, answer_type: str = "") -> str:
    """Normalize SymPy output to school-friendly notation."""
    s = (value or "").strip()
    if not s:
        return s
    if is_prose_answer(s):
        return "нет корней"

    at = (answer_type or "").lower()

    # x=-7/3 style for equation solutions
    if at == "equation_solution":
        if re.search(r"\([^)]*;[^)]*\)", s):
            return s
        if "," in s and s.count("=") >= 2:
            parts = [p.strip() for p in s.split(",") if p.strip()]
            if len(parts) >= 2 and all(re.match(r"^[a-zA-Z_]", p) for p in parts):
                return ", ".join(format_school_notation(p, at) for p in parts)
        m = re.match(r"^([a-zA-Z])\s*=\s*(.+)$", s)
        if m:
            var, rhs = m.group(1), m.group(2).strip()
            if "±" in rhs:
                return f"{var} = {rhs}"
            rhs = _format_numeric_rhs(rhs)
            return f"{var} = {rhs}"
        if "±" in s or ";" in s:
            return s
        return _format_numeric_rhs(s)

    if at in ("exact_number", "decimal", "fraction"):
        return _format_numeric_rhs(s)

    if at in ("expression", "fraction"):
        return format_expression_school(s)

    return s


def answer_needs_school_format(s: str, answer_type: str = "") -> bool:
    """True if answer looks like raw SymPy output worth reformatting."""
    s = (s or "").strip()
    if not s:
        return False
    at = (answer_type or "").lower()
    if at not in ("expression", "fraction"):
        return bool(re.search(r"\*\*|Simplify\s*\(", s, re.I))
    if re.search(r"\*\*|Simplify\s*\(", s, re.I):
        return True
    if re.search(r"\d\.\d{7,}", s):
        return True
    if re.search(r"(?<=\d)[eE][+-]\d{2,}", s):
        return True
    if re.search(r"0\.\d{6,}", s):
        return True
    return False


def format_expression_school(value: str) -> str:
    """SymPy/raw algebra string → school notation (fractions, a^{n}, \\sqrt{})."""
    s = (value or "").strip()
    if not s:
        return s
    if is_prose_answer(s):
        return "нет корней"

    if ";" in s:
        return "; ".join(_format_labeled_part(p) for p in _split_expression_parts(s))

    return _format_expression_part(s)


def _split_expression_parts(s: str) -> list[str]:
    return [p.strip() for p in s.split(";") if p.strip()]


_LABELED_PART_RE = re.compile(
    r"^([абвгдежзийклмнопрстуфхцчшщъыьэюя]\)|\d+\))\s*(.*)$",
    re.I,
)


def _format_labeled_part(segment: str) -> str:
    segment = (segment or "").strip()
    m = _LABELED_PART_RE.match(segment)
    if m:
        return f"{m.group(1)} {_format_expression_part(m.group(2).strip())}"
    return _format_expression_part(segment)


def _format_expression_part(part: str) -> str:
    part = (part or "").strip()
    if not part:
        return part
    m = re.match(r"^([a-zA-Z])\s*=\s*(.+)$", part)
    if m:
        rhs = _format_algebraic_string(m.group(2).strip())
        return f"{m.group(1)} = {rhs}"
    return _format_algebraic_string(part)


def _unwrap_sympy_call(s: str) -> str:
    s = (s or "").strip()
    m = re.match(r"^Simplify\s*\((.+)\)\s*$", s, re.I | re.S)
    return m.group(1).strip() if m else s


def _format_algebraic_string(s: str) -> str:
    s = _unwrap_sympy_call((s or "").strip())
    if not s:
        return s

    if re.fullmatch(r"[\d.,]+[eE][+-]?\d+", s):
        try:
            return _format_scientific_school(float(s.replace(",", ".")))
        except ValueError:
            pass

    # Already school-like LaTeX (keep \sqrt, \frac)
    if "\\sqrt" in s or "\\frac" in s:
        if "**" not in s and not re.search(r"Simplify\s*\(", s, re.I):
            if not re.search(r"\d\.\d{7,}", s):
                return s

    expr = parse_expr(_latexish_to_sympy(s))
    if expr is None:
        try:
            import sympy

            expr = sympy.sympify(_unwrap_sympy_call(s))
        except Exception:
            return _sympy_str_light_cleanup(s)
    if expr is None:
        return _sympy_str_light_cleanup(s)
    return _expr_to_school_notation(expr)


def _sympy_str_light_cleanup(s: str) -> str:
    s = _unwrap_sympy_call(s)
    s = s.replace("**", "^")
    s = re.sub(r"\^(\([^)]+\))", r"^{\1}", s)
    s = re.sub(r"\^(-?\d+)", r"^{\1}", s)
    return s


def _format_scientific_school(f: float) -> str:
    import math

    if f == 0:
        return "0"
    exp = int(math.floor(math.log10(abs(f))))
    mantissa = round(f / (10**exp), 4)
    if abs(mantissa - round(mantissa)) < 1e-9:
        mantissa_str = str(int(round(mantissa)))
    else:
        mantissa_str = str(mantissa).rstrip("0").rstrip(".").replace(".", ",")
    return f"{mantissa_str} * 10^{{{exp}}}"


def _format_pure_number(expr: Any) -> str:
    import sympy
    from sympy import N

    if expr.is_Integer:
        return str(int(expr))
    if expr.is_Rational:
        p, q = expr.as_numer_denom()
        if q == 1:
            return str(int(p))
        return f"{int(p)}/{int(q)}"
    try:
        f = float(N(expr))
    except Exception:
        return str(expr)
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    if abs(f) < 1e-4 or abs(f) >= 1e6:
        return _format_scientific_school(f)
    return str(round(f, 6)).rstrip("0").rstrip(".").replace(".", ",")


def _latex_to_school(ltx: str) -> str:
    s = (ltx or "").strip()
    s = s.replace(r"\cdot", " ").replace(r"\times", " ")
    s = re.sub(r"\\left|\\right", "", s)

    def _frac_repl(m: re.Match) -> str:
        a, b = m.group(1).strip(), m.group(2).strip()
        if re.fullmatch(r"-?\d+", a) and re.fullmatch(r"-?\d+", b):
            return f"{a}/{b}"
        return rf"\frac{{{a}}}{{{b}}}"

    s = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", _frac_repl, s)
    s = re.sub(r"\\sqrt\[3\]\{([^}]+)\}", r"∛(\1)", s)
    s = re.sub(r"\\sqrt\{([^}]+)\}", r"\\sqrt{\1}", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_valid_sympy_expr(expr: Any) -> bool:
    """Reject singletons / non-expression objects that crash simplify()."""
    try:
        from sympy.core.basic import Basic
    except ImportError:
        return expr is not None
    if not isinstance(expr, Basic):
        return False
    # sympy.S (SingletonRegistry) is Basic but not a mathematical expression.
    if type(expr).__name__ == "SingletonRegistry":
        return False
    return hasattr(expr, "free_symbols") or getattr(expr, "is_Number", False)


def _expr_to_school_notation(expr: Any) -> str:
    import sympy
    from sympy import N, latex, nsimplify, simplify

    if expr is None:
        return ""
    if not _is_valid_sympy_expr(expr):
        return _sympy_str_light_cleanup(str(expr))

    try:
        e = simplify(expr)
    except Exception:
        log.debug("_expr_to_school_notation: simplify failed", exc_info=True)
        return _sympy_str_light_cleanup(str(expr))

    if e.is_Number:
        return _format_pure_number(e)

    try:
        e = nsimplify(e, rational=True, tolerance=1e-12)
        e = simplify(e)
    except Exception:
        pass

    if e.is_Number:
        return _format_pure_number(e)

    try:
        f = float(N(e))
        if e.is_Float or (e.is_Number and not e.is_Rational and not e.is_Integer):
            if abs(f) < 1e-4 or abs(f) >= 1e6:
                return _format_scientific_school(f)
            if abs(f - round(f)) < 1e-9:
                return str(int(round(f)))
            return str(round(f, 6)).rstrip("0").rstrip(".").replace(".", ",")
    except Exception:
        pass

    try:
        return _latex_to_school(
            latex(
                e,
                mul_symbol=" ",
                fold_frac_powers=True,
                fold_short_frac=True,
                inv_trig_style="full",
            )
        )
    except Exception:
        return _sympy_str_light_cleanup(str(e))


def beautify_answer_if_equivalent(answer: str, answer_type: str) -> str:
    """Reformat to school notation when the expression parses (same math guaranteed)."""
    s = (answer or "").strip()
    if not s or not answer_needs_school_format(s, answer_type):
        return s
    if not _expression_parseable(s):
        return s
    pretty = format_school_notation(s, answer_type)
    return pretty if pretty and pretty != s else s


def _expression_parseable(s: str) -> bool:
    """True if every math segment of a (possibly multipart) answer parses."""
    for segment in _split_expression_parts(s):
        body = _LABELED_PART_RE.match(segment)
        part = body.group(2).strip() if body else segment
        fm = re.match(r"^([a-zA-Z])\s*=\s*(.+)$", part)
        part = fm.group(2).strip() if fm else part
        part = _unwrap_sympy_call(part)
        if re.fullmatch(r"[\d.,]+[eE][+-]?\d+", part):
            continue
        if parse_expr(_latexish_to_sympy(part)) is None:
            try:
                import sympy

                sympy.sympify(part)
            except Exception:
                return False
    return True


def _find_top_level_slash_index(s: str) -> int | None:
    """Index of division `/` outside `{...}` (e.g. `a^{2} / 3`, `-a\\sqrt{6}/3`)."""
    depth = 0
    for i, ch in enumerate(s):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == "/" and depth == 0:
            if s[:i].strip() and s[i + 1 :].strip():
                return i
    return None


def _slash_to_display_frac(s: str) -> str:
    """School `3 / \\sqrt{a}` → display `\\frac{3}{\\sqrt{a}}`."""
    s = (s or "").strip()
    if not s:
        return s
    idx = _find_top_level_slash_index(s)
    if idx is None:
        return s
    left = s[:idx].strip()
    right = s[idx + 1 :].strip()
    return rf"\frac{{{left}}}{{{right}}}"


def _normalize_math_exponents(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\^(\d+)", r"^{\1}", s)
    s = re.sub(r"\^([a-zA-Z])", r"^{\1}", s)
    return s


def _normalize_display_spacing(s: str) -> str:
    """Minor KaTeX polish: `9 a` → `9a`, tight `a b` products."""
    s = (s or "").strip()
    if re.fullmatch(r"-?\d+\s+[a-zA-Z]", s):
        return re.sub(r"(\d+)\s+([a-zA-Z])", r"\1\2", s)
    return s


def _needs_math_wrap(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return False
    if re.fullmatch(r"[\d.,]+[eE][+-]?\d+", s):
        return True
    if re.fullmatch(r"-?\d+$", s):
        return True
    if re.fullmatch(r"-?\d+[.,]\d+", s):
        return True
    if re.fullmatch(r"-?\d+\s+\d+/\d+", s):
        return True
    if _find_top_level_slash_index(s) is not None:
        return True
    if re.fullmatch(r"-?\d+\s*[a-zA-Z]", s):
        return True
    if re.fullmatch(r"[a-zA-Z]", s):
        return True
    return bool(
        re.search(r"\\frac|\\sqrt|\^|±|√|[a-zA-Z].*[\+\-\*/=]|\\", s)
    )


def _latex_math_content(s: str) -> str:
    """Inner LaTeX (without $ delimiters)."""
    s = (s or "").strip()
    short_dec = _short_decimal_latex(s)
    if short_dec is not None:
        return short_dec
    m = re.fullmatch(r"(\d+)\s+(\d+)/(\d+)", s)
    if m:
        return rf"{m.group(1)}\frac{{{m.group(2)}}}{{{m.group(3)}}}"
    m = re.fullmatch(
        r"([\d.,]+)\s*(?:\*|×|·)?\s*10\^\{?(-?\d+)\}?\s*(?:г|кг)?",
        s,
        re.I,
    )
    if m:
        mant = m.group(1).replace(",", "{,}")
        return rf"{mant} \cdot 10^{{{m.group(2)}}}"
    s = _slash_to_display_frac(s)
    s = _normalize_display_spacing(s)
    return _normalize_math_exponents(s)


def _wrap_math_body(body: str) -> str:
    body = (body or "").strip()
    if not body:
        return body
    fm = re.match(r"^([a-zA-Z])\s*=\s*(.+)$", body)
    if fm:
        return f"${fm.group(1)} = {_latex_math_content(fm.group(2).strip())}$"
    if _needs_math_wrap(body):
        return f"${_latex_math_content(body)}$"
    return body


def _split_equation_solution_parts(s: str) -> list[str]:
    """Split `x=a; x=b`, `x=a, x=b`, `x_1=…, x_2=…`, multipart `а) …; б) …`."""
    s = (s or "").strip()
    if not s:
        return []
    if ";" in s:
        return [p.strip() for p in _split_expression_parts(s) if p.strip()]

    chunks = re.split(r",\s*([a-zA-Z_]\w*)\s*=\s*", s)
    if len(chunks) > 1:
        out = [chunks[0].strip()]
        for i in range(1, len(chunks), 2):
            if i + 1 < len(chunks):
                out.append(f"{chunks[i]} = {chunks[i + 1].strip().rstrip(',')}")
        return out
    return [s]


def _normalize_equation_rhs_for_parse(rhs: str) -> str:
    rhs = (rhs or "").strip().rstrip(",")
    rhs = re.sub(r"√\(([^)]+)\)", r"sqrt(\1)", rhs)
    rhs = re.sub(r"√(\d+)", r"sqrt(\1)", rhs)
    rhs = rhs.replace("\\pm", "±")
    return re.sub(r"(\d),(\d)", r"\1.\2", rhs)


def _latex_sqrt_literal(rhs: str) -> str | None:
    """`sqrt(6)`, `√(20.5)` → `\\sqrt{…}` without bogus variable parsing."""
    s = (rhs or "").strip()
    m = re.fullmatch(r"sqrt\(([^)]+)\)", _normalize_equation_rhs_for_parse(s))
    if not m:
        return None
    inner = m.group(1).strip()
    try:
        from sympy import N, latex, nsimplify, sqrt

        expr = parse_expr(_latexish_to_sympy(f"sqrt({inner})"))
        if expr is not None and abs(float(N(expr)) - float(N(expr))) < 1e-9:
            ltx = latex(expr, mul_symbol=" ", fold_short_frac=False)
            if r"\sqrt" in ltx:
                return ltx
    except Exception:
        pass
    return rf"\sqrt{{{inner.replace(',', '{,}')}}}"


def _short_decimal_latex(rhs: str) -> str | None:
    """Keep school decimals in LaTeX (8.5 → 8{,}5) when ≤2 fractional digits."""
    s = (rhs or "").strip()
    m = re.fullmatch(r"(-?\d+)[.,](\d+)", s)
    if not m or len(m.group(2)) > 2:
        return None
    return f"{m.group(1)}{{,}}{m.group(2)}"


def _latex_equation_rhs(rhs: str) -> str:
    """KaTeX inner math for equation RHS (fractions, surds, ±)."""
    rhs = (rhs or "").strip().rstrip(",")
    if not rhs:
        return rhs

    short_dec = _short_decimal_latex(rhs)
    if short_dec is not None:
        return short_dec

    if re.fullmatch(r"-?\d+,\d+", rhs):
        return rhs.replace(",", "{,}")

    if re.fullmatch(r"-?\d+\.\d+", rhs):
        try:
            from sympy import N, latex, nsimplify, sqrt

            f = float(rhs)
            for d in (2, 3, 5, 6, 7, 10, 11, 13, 17, 19):
                cand = nsimplify(f, [sqrt(d)], tolerance=1e-6)
                if abs(float(N(cand)) - f) < 1e-6:
                    return latex(cand, mul_symbol=" ", fold_short_frac=False)
            rat = nsimplify(f, rational=True, tolerance=1e-9)
            if rat.is_Rational:
                _p, q = rat.as_numer_denom()
                if q <= 60:
                    return latex(rat, fold_short_frac=False)
            if abs(f - round(f)) < 1e-9:
                return str(int(round(f)))
        except Exception:
            pass

    if rhs.startswith("±"):
        inner = rhs[1:].strip()
        lit = _latex_sqrt_literal(inner)
        if lit:
            return rf"\pm {lit}"
        return rf"\pm {_latex_equation_rhs(inner)}"

    lit = _latex_sqrt_literal(rhs)
    if lit:
        return lit

    if "±" in rhs:
        parts = re.split(r"\s*±\s*", rhs, maxsplit=1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return rf"{_latex_equation_rhs(parts[0].strip())} \pm {_latex_equation_rhs(parts[1].strip())}"

    if r"\pm" in rhs:
        parts = re.split(r"\\pm", rhs, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            left = _latex_equation_rhs(parts[0].strip())
            right = _latex_equation_rhs(parts[1].strip())
            return rf"{left} \pm {right}"

    parse_s = _normalize_equation_rhs_for_parse(rhs)
    try:
        import sympy
        from sympy import latex

        expr = parse_expr(_latexish_to_sympy(parse_s))
        if expr is None:
            expr = sympy.sympify(parse_s)
        if expr is not None:
            ltx = latex(expr, mul_symbol=" ", fold_short_frac=False)
            ltx = ltx.replace(r"\cdot", " ").replace(r"\left", "").replace(r"\right", "")
            return ltx
    except Exception:
        pass

    body = rhs.replace("√", r"\sqrt")
    body = re.sub(r"sqrt\(([^)]+)\)", r"\\sqrt{\1}", body)
    return _slash_to_display_frac(body)


def _wrap_equation_solution(part: str) -> str:
    part = (part or "").strip()
    if is_prose_answer(part):
        return "нет корней"
    m = re.match(r"^([a-zA-Z_]\w*)\s*=\s*(.+)$", part)
    if m:
        return f"${m.group(1)} = {_latex_equation_rhs(m.group(2))}$"
    inner = _latex_equation_rhs(part)
    if inner != part or re.search(r"[\d/\\^√±]", part):
        return f"${inner}$"
    return part


def _to_equation_answer_latex(answer: str) -> str:
    raw = (answer or "").strip()
    if not raw or is_prose_answer(raw):
        return raw

    parts = _split_equation_solution_parts(raw)
    rendered: list[str] = []
    for part in parts:
        labeled = _LABELED_PART_RE.match(part)
        if labeled:
            rendered.append(f"{labeled.group(1)} {_wrap_equation_solution(labeled.group(2).strip())}")
        else:
            rendered.append(_wrap_equation_solution(part))

    if ";" in raw:
        return "; ".join(rendered)
    if len(rendered) > 1:
        return ", ".join(rendered)
    return rendered[0] if rendered else raw


_INEQUALITY_RE = re.compile(
    r"^([a-zA-Z_]\w*)\s*(<=|>=|≤|≥|<|>)\s*(.+)$",
    re.I,
)


def _latex_inequality_op(op: str) -> str:
    op = (op or "").strip()
    return {"≤": r"\le", "≥": r"\ge"}.get(op, op)


def _wrap_single_inequality(part: str) -> str:
    part = (part or "").strip()
    if not part or is_prose_answer(part):
        return part
    m = _INEQUALITY_RE.match(part.replace("≤", "<=").replace("≥", ">="))
    if not m:
        return _latex_labeled_part(part)
    var, op, rhs = m.group(1), _latex_inequality_op(m.group(2)), m.group(3).strip()
    return f"${var} {op} {_latex_equation_rhs(rhs)}$"


def _to_inequality_answer_latex(answer: str) -> str:
    raw = (answer or "").strip()
    if not raw or is_prose_answer(raw):
        return raw
    if ";" in raw:
        return "; ".join(_wrap_single_inequality(p) for p in _split_expression_parts(raw))
    return _wrap_single_inequality(raw)


def _latex_labeled_part(segment: str) -> str:
    segment = (segment or "").strip()
    m = _LABELED_PART_RE.match(segment)
    if m:
        return f"{m.group(1)} {_wrap_math_body(m.group(2).strip())}"
    return _wrap_math_body(segment)


_COORD_PAIR_RE = re.compile(r"\(\s*([^;)]+?)\s*;\s*([^)]+?)\s*\)")


def _latex_coord_component(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return s
    if "\\sqrt" in s or "\\frac" in s:
        return s.replace(",", "{,}")
    if re.fullmatch(r"-?[\d]+,[\d]+", s):
        return s.replace(",", "{,}")
    if re.fullmatch(r"-?[\d]+\.[\d]+", s):
        return s.replace(".", "{,}")
    return _latex_math_content(s)


def _latex_coord_pair(x: str, y: str) -> str:
    return f"({_latex_coord_component(x)}; {_latex_coord_component(y)})"


def _to_coordinate_answer_latex(answer: str) -> str:
    """Format coordinate pairs and labeled axis intersections for KaTeX."""
    raw = (answer or "").strip()
    if not raw:
        return ""
    matches = list(_COORD_PAIR_RE.finditer(raw))
    if not matches:
        return _latex_labeled_part(raw)

    out: list[str] = []
    last = 0
    for m in matches:
        if m.start() > last:
            gap = raw[last:m.start()]
            if gap.strip():
                out.append(gap)
        out.append(f"${_latex_coord_pair(m.group(1), m.group(2))}$")
        last = m.end()
    if last < len(raw):
        tail = raw[last:]
        if tail.strip():
            out.append(tail)
    return "".join(out)


def to_question_latex(question_text: str) -> str:
    """KaTeX-ready question: wrap math segments, keep Russian prose as-is."""
    raw = (question_text or "").strip()
    if not raw:
        return ""
    return "\n".join(_latexify_question_line(ln) for ln in raw.split("\n"))


_QUESTION_VERB_RE = re.compile(
    r"^(Найдите|Вычислите|Упростите|Сократите|Определите|Сравните|"
    r"Постройте|Докажите|Решите|Запишите|Представьте|Преобразуйте|"
    r"Разложите|Выразите|Изобразите|Составьте|Выполните)",
    re.I,
)


def _line_has_cyrillic_prose(s: str) -> bool:
    return bool(re.search(r"[а-яё]{5,}", (s or "").lower()))


def _latexify_question_line(line: str) -> str:
    line = (line or "").strip()
    if not line:
        return line
    if "$" in line:
        return line

    stripped = re.sub(r"^Решите\s+уравнени[ея]:\s*", "", line, flags=re.I).strip()

    if _line_has_cyrillic_prose(stripped):
        m = re.match(r"^([А-Яа-яЁё\s]+:?\s*)(.+)$", stripped)
        if m:
            prefix, body = m.group(1).strip(), m.group(2).strip()
            if (
                _QUESTION_VERB_RE.match(prefix)
                and _needs_math_wrap(body)
                and not _line_has_cyrillic_prose(body)
            ):
                wrapped = _wrap_math_body(body)
                if wrapped != body:
                    return f"{prefix} {wrapped}"
        return line

    if "=" in stripped and _needs_math_wrap(stripped) and not _line_has_cyrillic_prose(stripped):
        wrapped = _wrap_math_body(stripped)
        if wrapped != stripped:
            if re.match(r"^Решите\b", line, re.I):
                return wrapped
            return f"Решите уравнение: {wrapped}"

    if ";" in stripped:
        parts = _split_expression_parts(stripped)
        if len(parts) >= 2 and any(_needs_math_wrap(p) for p in parts):
            return "; ".join(_latex_labeled_part(p) for p in parts)

    if _LABELED_PART_RE.match(stripped):
        return _latex_labeled_part(stripped)

    if _needs_math_wrap(stripped) and not _line_has_cyrillic_prose(stripped):
        wrapped = _wrap_math_body(stripped)
        if wrapped != stripped:
            return wrapped

    return line


def to_answer_latex(answer: str, answer_type: str = "") -> str:
    """KaTeX-ready string: prose + `$math$` segments (for correct_answer_latex column)."""
    raw = (answer or "").strip()
    if not raw:
        return ""
    try:
        return _to_answer_latex_inner(raw, answer_type)
    except Exception:
        log.warning(
            "to_answer_latex failed for %r (%s)",
            raw[:120],
            answer_type,
            exc_info=True,
        )
        return raw


def _to_answer_latex_inner(answer: str, answer_type: str = "") -> str:
    raw = (answer or "").strip()
    if is_prose_answer(raw):
        return raw

    at = (answer_type or "").lower()
    if at == "equation_solution":
        return _to_equation_answer_latex(raw)

    if at == "inequality":
        return _to_inequality_answer_latex(raw)

    if at in ("exact_number", "decimal"):
        dec_lit = _short_decimal_latex(raw)
        if dec_lit:
            return f"${dec_lit}$"

    if at == "coordinate" or _COORD_PAIR_RE.search(raw):
        rendered = _to_coordinate_answer_latex(raw)
        if rendered and rendered != raw:
            return rendered

    school = (
        format_expression_school(raw)
        if at in ("expression", "fraction") or answer_needs_school_format(raw, at)
        else raw
    )

    if ";" in school and not _COORD_PAIR_RE.search(school):
        return "; ".join(_latex_labeled_part(p) for p in _split_expression_parts(school))
    return _latex_labeled_part(school)


def enrich_distractor_latex(
    distractor_meta: list | None,
    answer_type: str = "",
) -> list:
    """Add value_latex for MCQ option rendering."""
    out: list = []
    for item in distractor_meta or []:
        if not isinstance(item, dict):
            out.append(item)
            continue
        copy = dict(item)
        val = str(copy.get("value") or "").strip()
        if val and not copy.get("value_latex"):
            try:
                copy["value_latex"] = to_answer_latex(val, answer_type)
            except Exception:
                log.warning(
                    "enrich_distractor_latex: skip value_latex for %r",
                    val[:120],
                    exc_info=True,
                )
                copy["value_latex"] = val
        out.append(copy)
    return out


def _format_numeric_rhs(s: str) -> str:
    """Format numeric RHS: prefer int or simple fraction string."""
    s = s.strip()
    try:
        import sympy
        from sympy import N, Rational, nsimplify

        expr = parse_expr(_latexish_to_sympy(s))
        if expr is None:
            expr = sympy.sympify(s)
        if expr is None:
            return s
        simplified = sympy.simplify(expr)
        if simplified.is_Rational and not simplified.is_Integer:
            p, q = simplified.as_numer_denom()
            if q == 1:
                return str(int(p))
            return f"{int(p)}/{int(q)}"
        val = N(simplified)
        if val.is_real:
            f = float(val)
            if abs(f - round(f)) < 1e-9:
                return str(int(round(f)))
            return str(round(f, 10)).rstrip("0").rstrip(".")
        return str(nsimplify(simplified))
    except Exception:
        return s


def _format_sympy_result(result: Any, answer_type: str) -> Optional[str]:
    import sympy
    from sympy import Eq
    from sympy.sets import Range, Reals

    at = (answer_type or "").lower()

    if result is Reals or str(result) == "Reals":
        return "любое число"

    if isinstance(result, Range):
        try:
            vals = [int(x) for x in result]
            return ", ".join(str(v) for v in vals)
        except Exception:
            return str(result)

    if isinstance(result, Eq):
        try:
            sols = sympy.solve(result)
            return _format_solutions(sols, at)
        except Exception:
            return None

    if isinstance(result, dict):
        return _format_solutions(result, at)

    if isinstance(result, (list, tuple, set)):
        return _format_solutions(result, at)

    try:
        if hasattr(result, "free_symbols") and result.free_symbols:
            simplified = sympy.simplify(result)
            return str(simplified)
        from sympy import N

        val = N(result)
        if val.is_real:
            f = float(val)
            if abs(f - round(f)) < 1e-9:
                return str(int(round(f)))
            return str(round(f, 10)).rstrip("0").rstrip(".")
        return str(sympy.simplify(result))
    except Exception:
        try:
            return str(sympy.simplify(result))
        except Exception:
            return str(result) if result is not None else None


def _school_rhs_from_sympy(expr: Any) -> str:
    """Exact school notation: fractions, surds (2√2), integers."""
    import sympy
    from sympy import Rational, nsimplify

    e = sympy.simplify(expr)
    if e.is_Integer:
        return str(int(e))
    if isinstance(e, Rational) or e.is_Rational:
        p, q = e.as_numer_denom()
        if q == 1:
            return str(int(p))
        return f"{int(p)}/{int(q)}"

    coeff, rest = e.as_coeff_Mul()
    if getattr(rest, "is_Pow", False) and rest.exp == sympy.S.Half and rest.base.is_Integer:
        base = int(rest.base)
        c = sympy.simplify(coeff)
        surd = f"√{base}"
        if c == 1:
            return surd
        if c == -1:
            return f"-{surd}"
        if c.is_Integer:
            return f"{int(c)}{surd}"
        if c.is_Rational and c.q != 1:
            return f"{int(c.p)}/{int(c.q)}{surd}"

    simplified = nsimplify(e)
    out = str(simplified)
    out = out.replace("sqrt(", "√").replace(")", "")
    return out


def _solution_scalar(s: Any) -> Any:
    """Extract numeric/root value from a solve() entry (scalar or Eq)."""
    import sympy
    from sympy import Eq

    s = sympy.simplify(s)
    if isinstance(s, Eq):
        return sympy.simplify(s.rhs)
    return s


def _try_format_pm_pair(sols: list, var: str = "x") -> Optional[str]:
    """x = ± a when roots are negates (e.g. ±2√2)."""
    import sympy
    from sympy import Eq, N

    if len(sols) != 2:
        return None
    if any(isinstance(s, (list, tuple, dict, set)) for s in sols):
        return None

    raw_a, raw_b = sols[0], sols[1]
    if isinstance(raw_a, Eq) and isinstance(raw_b, Eq) and str(raw_a.lhs) == str(raw_b.lhs):
        var = str(raw_a.lhs)
    a, b = _solution_scalar(raw_a), _solution_scalar(raw_b)
    try:
        if sympy.simplify(a + b) != 0:
            return None
    except TypeError:
        return None
    try:
        mag = b if float(N(b)) > 0 else a
        if float(N(mag)) < 0:
            mag = -mag
    except Exception:
        mag = abs(a)
    rhs = _school_rhs_from_sympy(mag)
    return f"{var} = ± {rhs}"


def _format_indexed_roots(values: list[str], var: str = "x") -> str:
    """x_1 = a, x_2 = b for multiple distinct roots."""
    if not values:
        return ""
    if len(values) == 1:
        return f"{var} = {values[0]}"
    return ", ".join(f"{var}_{i + 1} = {v}" for i, v in enumerate(values))


def _format_solutions(sols: Any, answer_type: str) -> Optional[str]:
    import sympy

    if sols is None:
        return None
    if isinstance(sols, dict):
        parts = []
        for k in sorted(sols.keys(), key=str):
            v = sols[k]
            try:
                import sympy
                from sympy import N

                if isinstance(v, (int, float)):
                    val = format_school_notation(str(v), answer_type)
                else:
                    val = format_school_notation(
                        _school_rhs_from_sympy(sympy.simplify(v)), answer_type
                    )
            except Exception:
                val = str(v)
            parts.append(f"{k} = {val}")
        return ", ".join(parts) if parts else None
    if isinstance(sols, (list, tuple, set)):
        if not sols:
            return "нет корней"
        sol_list = list(sols)
        at = (answer_type or "").lower()
        if at == "equation_solution" and sol_list and all(
            isinstance(s, (list, tuple)) and len(s) == 2 for s in sol_list
        ):
            pairs: list[str] = []
            for s in sol_list:
                x = _school_rhs_from_sympy(sympy.simplify(s[0]))
                y = _school_rhs_from_sympy(sympy.simplify(s[1]))
                pairs.append(f"({x}; {y})")
            return ", ".join(pairs)
        if at == "equation_solution":
            pm = _try_format_pm_pair(sol_list)
            if pm:
                return pm

        flat: list[str] = []
        for s in sol_list:
            if isinstance(s, (list, tuple, set)):
                sub = _format_solutions(s, answer_type)
                if sub:
                    flat.append(sub)
            elif isinstance(s, dict):
                sub = _format_solutions(s, answer_type)
                if sub:
                    flat.append(sub)
            else:
                try:
                    import sympy
                    from sympy import N

                    if at == "equation_solution":
                        flat.append(_school_rhs_from_sympy(sympy.simplify(s)))
                        continue
                    val = N(s)
                    if val.is_real:
                        f = float(val)
                        if abs(f - round(f)) < 1e-9:
                            flat.append(str(int(round(f))))
                        else:
                            flat.append(str(round(f, 10)).rstrip("0").rstrip("."))
                    else:
                        flat.append(str(sympy.simplify(s)))
                except Exception:
                    flat.append(str(s))
        if at == "equation_solution" and flat and all(
            not re.match(r"^[x-zA-Z]", v) for v in flat
        ):
            return _format_indexed_roots(flat)
        return "; ".join(flat) if flat else None
    return str(sols)


def _parse_sympy_compatible_string(sympy_string: str) -> Any:
    """Parse LLM sympy_compatible_string in a restricted SymPy namespace."""
    import sympy
    from sympy import Eq, sympify

    raw = (sympy_string or "").strip()
    if not raw:
        raise ValueError("empty sympy_compatible_string")

    ns = _sympy_namespace()

    m = re.match(r"^solve\s*\((.+)\)\s*$", raw, re.DOTALL | re.I)
    if m:
        inner = m.group(1).strip()
        try:
            obj = eval(inner, {"__builtins__": {}}, ns)  # noqa: S307
            if isinstance(obj, Eq):
                return sympy.solve(obj)
            return eval(raw, {"__builtins__": {}}, ns)  # noqa: S307
        except Exception:
            pass

    if raw.startswith("Eq(") or raw.startswith("Ne("):
        try:
            # evaluate=False: Eq(x**2+9,0) must stay Eq, not BooleanFalse
            inner = raw[raw.index("(") + 1 : raw.rindex(")")]
            if "," in inner:
                lhs_s, rhs_s = inner.rsplit(",", 1)
                lhs = eval(lhs_s.strip(), {"__builtins__": {}}, ns)  # noqa: S307
                rhs = eval(rhs_s.strip(), {"__builtins__": {}}, ns)  # noqa: S307
                from sympy import Eq as SymEq, Ne as SymNe

                if raw.startswith("Eq("):
                    return SymEq(lhs, rhs, evaluate=False)
                return SymNe(lhs, rhs, evaluate=False)
            return eval(raw, {"__builtins__": {}}, ns)  # noqa: S307
        except Exception:
            pass

    if raw.startswith("{") and raw.endswith("}"):
        try:
            return eval(raw, {"__builtins__": {}}, ns)  # noqa: S307
        except Exception:
            pass

    if raw.startswith("["):
        from math import prod

        ns = _sympy_namespace()
        ns["sum"] = sum
        ns["prod"] = prod
        ns["max"] = max
        ns["min"] = min
        return eval(raw, {"__builtins__": {}}, ns)  # noqa: S307

    if ";" in raw and not raw.strip().lower().startswith("solve"):
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        if len(parts) >= 2:
            return [_parse_sympy_compatible_string(p) for p in parts]

    converted = _latexish_to_sympy(raw)
    try:
        return sympify(converted, locals=ns)
    except Exception:
        pass

    expr = parse_expr(converted)
    if expr is not None:
        return expr

    raise ValueError(f"cannot parse sympy_compatible_string: {raw[:80]!r}")


def evaluate_sympy_string(
    sympy_string: str,
    answer_type: str,
    *,
    question: str = "",
) -> Optional[str]:
    """
    Evaluate LLM sympy_compatible_string locally → canonical answer string.
    Returns None if evaluation fails.
    """
    try:
        obj = _parse_sympy_compatible_string(sympy_string)
    except Exception as exc:
        log.debug("evaluate_sympy_string parse failed: %s", exc)
        return None

    import sympy
    from sympy import Eq

    if obj is False or str(obj) == "False":
        return "нет корней"

    at = (answer_type or "").lower()

    if isinstance(obj, Eq):
        try:
            if is_write_equation_task(question):
                return format_equation_from_eq(obj)

            syms = list(obj.free_symbols)
            if syms:
                sols = sympy.solve(obj, syms[0])
            else:
                sols = sympy.solve(obj)
            if at == "equation_solution" and syms and isinstance(sols, list) and len(sols) == 1:
                var = syms[0]
                val = format_school_notation(str(sols[0]), at)
                return f"{var} = {val}"
            result = _format_solutions(sols, at)
            if result and is_prose_answer(result):
                return "нет корней"
            return format_school_notation(result, at) if result else None
        except Exception as exc:
            log.debug("solve Eq failed: %s", exc)
            return None

    if isinstance(obj, dict):
        return _format_solutions(obj, at)

    if at in ("expression", "fraction"):
        try:
            import sympy

            if isinstance(obj, (list, tuple)):
                parts: list[str] = []
                use_index = bool(re.search(r"\b1\)", question))
                for i, item in enumerate(obj, 1):
                    val = sympy.simplify(item)
                    from sympy import N

                    prefix = f"{i}) " if use_index else ""
                    try:
                        f = float(N(val))
                        if abs(f - round(f)) < 1e-8:
                            parts.append(f"{prefix}{int(round(f))}")
                        else:
                            parts.append(f"{prefix}{round(f, 6)}")
                    except Exception:
                        parts.append(f"{prefix}{format_expression_school(str(sympy.simplify(val)))}")
                return "; ".join(parts)
            simplified = sympy.simplify(obj)
            from src.pipeline.answer_sympy import eval_computed_for_question

            ev = eval_computed_for_question(question, str(simplified))
            if ev is not None:
                return ev
            return format_expression_school(str(simplified))
        except Exception:
            result = _format_sympy_result(obj, at)
            return format_school_notation(result, at) if result else None

    result = _format_sympy_result(obj, at)
    return format_school_notation(result, at) if result else None


@dataclass
class SympyGateResult:
    ok: bool
    computed_local: Optional[str] = None
    reason: str = ""


def solve_equation_from_question(question: str, answer_type: str = "equation_solution") -> Optional[str]:
    """Extract equation from question text, solve locally, return expected answer."""
    q = (question or "").strip()
    if not q:
        return None

    try:
        import sympy
        from sympy import Eq, solve
        from sympy.parsing.sympy_parser import (
            implicit_multiplication_application,
            parse_expr,
            standard_transformations,
        )
    except ImportError:
        return None

    transformations = standard_transformations + (implicit_multiplication_application,)
    locals_dict = _equation_parse_locals()

    for line in reversed(q.splitlines()):
        line = line.strip().rstrip(";").strip()
        if "=" not in line or not re.search(r"[0-9]", line):
            continue
        cleaned = _absify_pipes(_latexish_to_sympy(line))
        if "=" not in cleaned:
            continue
        lhs_s, rhs_s = cleaned.split("=", 1)
        try:
            l_expr = parse_expr(
                lhs_s.strip(),
                transformations=transformations,
                local_dict=locals_dict,
            )
            r_expr = parse_expr(
                rhs_s.strip(),
                transformations=transformations,
                local_dict=locals_dict,
            )
            eq = Eq(l_expr, r_expr)
            syms = list(eq.free_symbols)
            if not syms:
                continue
            sols = solve(eq, syms[0])
            if answer_type == "equation_solution" and len(sols) == 1:
                val = format_school_notation(str(sols[0]), answer_type)
                return f"{syms[0]} = {val}"
            expected = _format_solutions(sols, answer_type)
            if expected is None:
                continue
            return format_school_notation(expected, answer_type)
        except Exception:
            continue
    return None


def _try_validate_equation_answer(question: str, answer: str) -> Optional[bool]:
    """Solve equation from question text and compare to answer."""
    expected = solve_equation_from_question(question, "equation_solution")
    if expected is None:
        return None
    equiv = sympy_equivalent(expected, answer, "equation_solution")
    if equiv is not None:
        return equiv
    return None


def _normalize_sympy_relational_string(s: str) -> str:
    """Greater(20, 6) → 20 > 6; And(...) left as-is for answers_equivalent."""
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


def _integer_answer_from_computed_inequality(question: str, computed: str) -> Optional[str]:
    """Extract max/min integer when SymPy returns inequality but answer is a number."""
    import math

    from src.pipeline.answer_verify import _parse_single_inequality

    q = (question or "").lower()
    if "цел" not in q:
        return None
    max_w = any(w in q for w in ("наибольш", "максималь"))
    min_w = any(w in q for w in ("наименьш", "минималь"))
    if not max_w and not min_w:
        return None

    comp = _normalize_sympy_relational_string(computed)
    parsed = _parse_single_inequality(comp)
    if not parsed:
        return None
    _var, op, bound = parsed
    if max_w and op in ("<", "<="):
        n = math.floor(bound - 1e-9) if op == "<" else math.floor(bound + 1e-9)
        return str(n)
    if min_w and op in (">", ">="):
        n = math.ceil(bound + 1e-9) if op == ">" else math.ceil(bound - 1e-9)
        return str(n)
    return None


def _gate_match(
    *,
    computed: str,
    absolute_answer: str,
    stored_answer: str,
    answer_type: str,
    question: str,
) -> bool:
    from src.pipeline.answer_verify import answers_equivalent

    if answers_equivalent(computed, absolute_answer, answer_type, question=question):
        return True
    if stored_answer and answers_equivalent(stored_answer, computed, answer_type, question=question):
        return True
    if stored_answer and answers_equivalent(stored_answer, absolute_answer, answer_type, question=question):
        return True
    return False


def sympy_gate(
    sympy_string: str,
    absolute_answer: str,
    answer_type: str,
    *,
    question: str = "",
    stored_answer: str = "",
) -> SympyGateResult:
    """
    Verify LLM output: local eval of sympy_string must match absolute_correct_answer.
    Fallback: validate absolute_answer against question text when parse fails.
    """
    from src.pipeline.answer_verify import answers_equivalent, _coordinate_system_equivalent
    from src.pipeline.answer_sympy import try_validate_answer_for_question

    absolute_answer = (absolute_answer or "").strip()
    stored_answer = (stored_answer or "").strip()
    if not absolute_answer:
        return SympyGateResult(ok=False, reason="empty_absolute_answer")

    at = (answer_type or "").lower()

    if at == "multiple_choice":
        if answers_equivalent(stored_answer, absolute_answer, at, question=question):
            return SympyGateResult(
                ok=True,
                computed_local=absolute_answer,
                reason="sympy_match",
            )
        if _is_text_mcq_answer(absolute_answer) and stored_answer:
            if re.sub(r"\s+", "", stored_answer.lower()) == re.sub(
                r"\s+", "", absolute_answer.lower()
            ):
                return SympyGateResult(
                    ok=True,
                    computed_local=absolute_answer,
                    reason="textbook_agrees_with_llm",
                )

    computed = evaluate_sympy_string(sympy_string, answer_type, question=question)
    if computed is not None:
        computed = _normalize_sympy_relational_string(computed)

    if computed is not None and at == "multiple_choice":
        if _gate_match(
            computed=computed,
            absolute_answer=absolute_answer,
            stored_answer=stored_answer,
            answer_type=at,
            question=question,
        ):
            return SympyGateResult(
                ok=True,
                computed_local=stored_answer or absolute_answer,
                reason="sympy_match_stored",
            )

    if computed is not None and at == "exact_number":
        extracted = _integer_answer_from_computed_inequality(question, computed)
        if extracted and stored_answer and answers_equivalent(
            stored_answer, extracted, "exact_number", question=question
        ):
            return SympyGateResult(
                ok=True,
                computed_local=stored_answer,
                reason="integer_from_inequality",
            )

    if computed is not None and at == "set":
        from src.pipeline.answer_verify import _continuous_domain_exclusions

        cd = _continuous_domain_exclusions(computed)
        if cd is not None:
            ne_parts = []
            for h in sorted(cd):
                hv = str(int(h)) if abs(h - round(h)) < 1e-9 else str(h)
                ne_parts.append(f"x ≠ {hv}")
            for candidate in (", ".join(ne_parts),):
                if stored_answer and answers_equivalent(
                    stored_answer, candidate, "set", question=question
                ):
                    return SympyGateResult(
                        ok=True,
                        computed_local=stored_answer,
                        reason="sympy_match_stored",
                    )

    if computed is not None:
        if is_prose_answer(absolute_answer) and is_prose_answer(computed):
            return SympyGateResult(ok=True, computed_local="нет корней", reason="sympy_match")
        if is_write_equation_task(question):
            if answers_equivalent(computed, absolute_answer, answer_type, question=question):
                return SympyGateResult(ok=True, computed_local=computed, reason="sympy_match")
            if equation_form_equivalent(computed, absolute_answer):
                return SympyGateResult(ok=True, computed_local=computed, reason="sympy_match")
            if stored_answer and answers_equivalent(computed, stored_answer, answer_type, question=question):
                return SympyGateResult(ok=True, computed_local=computed, reason="sympy_match")
            if stored_answer and equation_form_equivalent(computed, stored_answer):
                return SympyGateResult(ok=True, computed_local=computed, reason="sympy_match")

        equiv = sympy_equivalent(computed, absolute_answer, answer_type)
        if equiv is not True and answers_equivalent(computed, absolute_answer, answer_type, question=question):
            equiv = True
        if equiv is True:
            return SympyGateResult(ok=True, computed_local=computed, reason="sympy_match")
        if (answer_type or "").lower() == "expression":
            from src.pipeline.answer_sympy import (
                eval_computed_for_question,
                try_validate_expression_answer,
                _validate_formula_with_cases,
            )

            fm_only = re.match(r"^([a-zA-Z])\s*=\s*(.+)$", absolute_answer.strip())
            if fm_only:
                rhs = fm_only.group(2).strip()
                if sympy_equivalent(computed or "", rhs, answer_type) is True:
                    return SympyGateResult(
                        ok=True,
                        computed_local=computed,
                        reason="sympy_match_formula_rhs",
                    )
                if answers_equivalent(computed or "", rhs, answer_type, question=question):
                    return SympyGateResult(
                        ok=True,
                        computed_local=computed,
                        reason="sympy_match_formula_rhs",
                    )

            ev = eval_computed_for_question(question, computed or "")
            if ev and answers_equivalent(ev, absolute_answer, answer_type, question=question):
                return SympyGateResult(
                    ok=True,
                    computed_local=ev,
                    reason="sympy_match_substituted",
                )
            if try_validate_expression_answer(question, absolute_answer) is True:
                return SympyGateResult(
                    ok=True,
                    computed_local=computed,
                    reason="question_validated_llm",
                )
            if try_validate_expression_answer(question, computed or "") is True:
                return SympyGateResult(
                    ok=True,
                    computed_local=computed,
                    reason="question_validated_computed",
                )
            parts_a = split_answer_parts(absolute_answer)
            if len(parts_a) >= 2 and re.search(r"[а-я]\)\s*[a-zA-Z]\s*=", question, re.I):
                if _validate_formula_with_cases(question, absolute_answer, computed or ""):
                    return SympyGateResult(
                        ok=True,
                        computed_local=computed,
                        reason="sympy_match_formula",
                    )
                # computed may be expanded form, e.g. (47*v+60)/(v*(v+2))
                if _validate_formula_with_cases(
                    question,
                    absolute_answer,
                    str(sympy_string or computed or ""),
                ):
                    return SympyGateResult(
                        ok=True,
                        computed_local=computed,
                        reason="sympy_match_formula",
                    )
            cp, ap = split_answer_parts(computed or ""), split_answer_parts(absolute_answer)
            if len(cp) >= 2 and len(cp) == len(ap):
                part_eq = [sympy_equivalent(c, a, answer_type) for c, a in zip(cp, ap)]
                if all(r is True for r in part_eq):
                    return SympyGateResult(
                        ok=True,
                        computed_local=computed,
                        reason="sympy_match_multipart",
                    )
        if equiv is False:
            # LLM prose wrong — trust local eval if it matches textbook or solves question
            if _gate_match(
                computed=computed,
                absolute_answer=absolute_answer,
                stored_answer=stored_answer,
                answer_type=answer_type,
                question=question,
            ):
                return SympyGateResult(
                    ok=True,
                    computed_local=stored_answer or computed,
                    reason="sympy_match_stored",
                )
            if (answer_type or "").lower() == "equation_solution":
                if _try_validate_equation_answer(question, computed) is True:
                    return SympyGateResult(
                        ok=True,
                        computed_local=computed,
                        reason="sympy_match",
                    )
            if stored_answer and (answer_type or "").lower() == "expression":
                from src.pipeline.answer_sympy import try_validate_expression_answer

                if try_validate_expression_answer(question, stored_answer) is True:
                    return SympyGateResult(
                        ok=True,
                        computed_local=stored_answer,
                        reason="sympy_match_stored",
                    )
                if answers_equivalent(stored_answer, computed, answer_type, question=question):
                    return SympyGateResult(
                        ok=True,
                        computed_local=stored_answer,
                        reason="sympy_match_stored",
                    )
            return SympyGateResult(
                ok=False,
                computed_local=computed,
                reason=f"local_mismatch: {computed!r} vs {absolute_answer!r}",
            )

    q_valid = try_validate_answer_for_question(question, absolute_answer, answer_type)
    if q_valid is True:
        return SympyGateResult(
            ok=True,
            computed_local=computed,
            reason="question_validated_fallback",
        )

    if (answer_type or "").lower() == "expression":
        from src.pipeline.answer_sympy import try_validate_expression_answer

        if try_validate_expression_answer(question, absolute_answer) is True:
            return SympyGateResult(
                ok=True,
                computed_local=absolute_answer,
                reason="question_validated_fallback",
            )
        if stored_answer and answers_equivalent(stored_answer, absolute_answer, answer_type, question=question):
            return SympyGateResult(
                ok=True,
                computed_local=absolute_answer,
                reason="textbook_agrees_with_llm",
            )

    if (answer_type or "").lower() == "equation_solution":
        eq_valid = _try_validate_equation_answer(question, absolute_answer)
        if eq_valid is True:
            solved = solve_equation_from_question(question, answer_type)
            return SympyGateResult(
                ok=True,
                computed_local=solved or computed,
                reason="equation_solved_fallback",
            )
        if eq_valid is False:
            return SympyGateResult(
                ok=False,
                computed_local=computed,
                reason="equation_mismatch_fallback",
            )

    if computed is None:
        if stored_answer and answers_equivalent(stored_answer, absolute_answer, answer_type, question=question):
            return SympyGateResult(
                ok=True,
                computed_local=absolute_answer,
                reason="textbook_agrees_with_llm",
            )
        stripped_parts = split_answer_parts(absolute_answer)
        if len(stripped_parts) == 1 and stripped_parts[0] != absolute_answer:
            stripped = stripped_parts[0]
            q_valid = try_validate_answer_for_question(question, stripped, answer_type)
            if q_valid is True:
                return SympyGateResult(
                    ok=True,
                    computed_local=stripped,
                    reason="question_validated_fallback",
                )
            if stored_answer and answers_equivalent(
                stored_answer, stripped, answer_type, question=question
            ):
                return SympyGateResult(
                    ok=True,
                    computed_local=stripped,
                    reason="textbook_agrees_with_llm",
                )
        return SympyGateResult(ok=False, reason="eval_failed")

    a = re.sub(r"\s+", "", (computed or "").lower())
    b = re.sub(r"\s+", "", absolute_answer.lower())
    if a == b:
        return SympyGateResult(ok=True, computed_local=computed, reason="string_match")

    # Local eval succeeded; trust computed when it solves the question
    if computed is not None:
        if answers_equivalent(computed, absolute_answer, answer_type, question=question):
            return SympyGateResult(ok=True, computed_local=computed, reason="sympy_match")
        if (answer_type or "").lower() == "equation_solution":
            if _try_validate_equation_answer(question, computed) is True:
                return SympyGateResult(
                    ok=True,
                    computed_local=computed,
                    reason="sympy_match",
                )

    if stored_answer and computed is not None and answers_equivalent(
        stored_answer, computed, answer_type, question=question
    ):
        return SympyGateResult(
            ok=True,
            computed_local=computed,
            reason="sympy_match",
        )

    if stored_answer and answers_equivalent(stored_answer, absolute_answer, answer_type, question=question):
        return SympyGateResult(
            ok=True,
            computed_local=stored_answer,
            reason="textbook_agrees_with_llm",
        )

    at_gate = (answer_type or "").lower()
    if at_gate == "equation_solution" and stored_answer:
        for cand in (computed, absolute_answer):
            if cand and _coordinate_system_equivalent(stored_answer, cand):
                return SympyGateResult(
                    ok=True,
                    computed_local=stored_answer,
                    reason="sympy_match_stored",
                )
        if is_prose_answer(absolute_answer) and is_prose_answer(stored_answer):
            return SympyGateResult(ok=True, computed_local=stored_answer, reason="sympy_match_stored")

    if at_gate == "expression" and stored_answer:
        sp = split_answer_parts(stored_answer)
        for cand in (computed, absolute_answer):
            if not cand:
                continue
            cp = split_answer_parts(cand)
            if len(sp) >= 2 and cp and sympy_equivalent(sp[0], cp[0], "expression") is True:
                if len(sp) == 1 or len(cp) >= len(sp):
                    if all(
                        sympy_equivalent(a, b, "expression") is True
                        for a, b in zip(sp, cp[: len(sp)])
                    ):
                        return SympyGateResult(
                            ok=True,
                            computed_local=stored_answer,
                            reason="sympy_match_stored",
                        )
                elif len(sp) >= 2 and len(cp) == 1:
                    return SympyGateResult(
                        ok=True,
                        computed_local=stored_answer,
                        reason="sympy_match_stored",
                    )

    return SympyGateResult(
        ok=False,
        computed_local=computed,
        reason="undecidable_equivalence",
    )


def resolve_canonical_answer(
    gate: SympyGateResult,
    llm_answer: str,
    *,
    question: str = "",
    answer_type: str = "",
    sympy_string: str = "",
) -> tuple[str, str]:
    """
    Pick DB canonical answer after gate passed.
    Returns (canonical_answer, source_tag).
    source_tag: local_sympy | equation_solved | llm_fallback
    """
    llm_answer = (llm_answer or "").strip()
    at = (answer_type or "").lower()
    reason = gate.reason or ""

    if reason == "textbook_agrees_with_llm":
        return llm_answer, "llm_fallback"

    if reason in CANONICAL_REASONS and gate.computed_local:
        return format_school_notation(gate.computed_local, at), "local_sympy"

    if reason == "equation_solved_fallback":
        solved = solve_equation_from_question(question, at) or gate.computed_local
        if solved:
            return format_school_notation(solved, at), "equation_solved"

    if reason == "question_validated_fallback":
        if sympy_string:
            ev = evaluate_sympy_string(sympy_string, at, question=question)
            if ev:
                return format_school_notation(ev, at), "local_sympy"
        if gate.computed_local:
            return format_school_notation(gate.computed_local, at), "local_sympy"
        return llm_answer, "llm_fallback"

    if gate.computed_local:
        return format_school_notation(gate.computed_local, at), "local_sympy"

    return llm_answer, "llm_fallback"
