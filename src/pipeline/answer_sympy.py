"""SymPy-backed answer comparison for verify pipeline."""
from __future__ import annotations

import logging
import random
import re
from typing import Optional

log = logging.getLogger(__name__)

import signal
from contextlib import contextmanager

class TimeoutException(Exception):
    pass

@contextmanager
def timeout_limit(seconds: int):
    def signal_handler(signum, frame):
        raise TimeoutException("Timed out!")
    
    old_handler = None
    try:
        old_handler = signal.signal(signal.SIGALRM, signal_handler)
        signal.alarm(seconds)
    except ValueError:
        pass
        
    try:
        yield
    finally:
        try:
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
        except ValueError:
            pass

def safe_simplify(expr, timeout: int = 3):
    import sympy
    try:
        with timeout_limit(timeout):
            return sympy.simplify(expr)
    except Exception as e:
        log.warning("sympy.simplify timed out or failed: %s", e)
        return expr


def timeout_default(seconds: int = 5, default_val = None):
    """Decorator: run func with SIGALRM timeout; return default_val on timeout or error."""
    def decorator(func):
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                with timeout_limit(seconds):
                    return func(*args, **kwargs)
            except TimeoutException:
                log.warning("Function %s timed out after %ds", func.__name__, seconds)
                return default_val
            except Exception as e:
                log.debug("Function %s failed: %s: %s", func.__name__, type(e).__name__, e)
                return default_val
        return wrapper
    return decorator



_SYMBOL_NAMES = "abcdefghijklmnopqrsuvwxyz"


def _latexish_to_sympy(s: str) -> str:
    s = (s or "").strip()
    sci_tokens: list[str] = []

    def _stash_sci(m: re.Match) -> str:
        sci_tokens.append(m.group(0))
        return f"__SCI{len(sci_tokens) - 1}__"

    s = re.sub(r"\d+\.?\d*[eE][+-]?\d+", _stash_sci, s)
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = re.sub(r"√(\d+(?:\.\d+)?)", r"sqrt(\1)", s)
    s = re.sub(r"√([a-zA-Z])", r"sqrt(\1)", s)
    s = s.replace("√", "sqrt").replace("×", "*").replace("·", "*")
    s = s.replace("^", "**")
    s = re.sub(r"\\sqrt\{([^}]+)\}", r"sqrt(\1)", s)
    s = re.sub(r"\\sqrt\[3\]\{([^}]+)\}", r"(\1)**(1/3)", s)
    # Both \frac and \dfrac are emitted by the LaTeX backfill. They have the
    # same mathematical meaning and must reach the same local verifier.
    s = re.sub(r"\\d?frac\{([^}]+)\}\{([^}]+)\}", r"((\1)/(\2))", s)
    s = re.sub(r"\$", "", s)
    s = re.sub(r"\\left|\\right", "", s)
    s = re.sub(r"\\cdot", "*", s)
    s = re.sub(r"\\times", "*", s)
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    # LaTeX / school exponents: a^{-10}, a**{-10}, ^{12}
    s = re.sub(r"\*\*\{([^}]+)\}", r"**(\1)", s)
    s = re.sub(r"\^\{([^}]+)\}", r"**(\1)", s)
    s = re.sub(r"([a-zA-Z0-9\)])\{(-?[^}]+)\}", r"\1**(\2)", s)
    # implicit multiplication: 2n, 4a, 1/7 a, )b, **(-10)b
    s = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", s)
    s = re.sub(r"(\d)\s+([a-zA-Z(])", r"\1*\2", s)
    s = re.sub(r"\)\s*([a-zA-Z])", r")*\1", s)
    s = re.sub(r"(\*\*\([^)]+\))([a-zA-Z])", r"\1*\2", s)
    s = re.sub(r"([a-zA-Z0-9\)])(\s+)([a-zA-Z(])", r"\1*\3", s)
    s = re.sub(r"\)\s*\(", r")*(", s)
    s = re.sub(r"sqrt\*\(", "sqrt(", s)
    for i, tok in enumerate(sci_tokens):
        s = s.replace(f"__SCI{i}__", tok)

    # Clean up redundant infinity boundaries in relations (e.g. (m >= 16/3) & (m < oo) -> m >= 16/3)
    s = re.sub(r"\s*&\s*\(\s*[a-zA-Z_]\w*\s*<\s*oo\s*\)", "", s)
    s = re.sub(r"\s*&\s*\(\s*oo\s*>\s*[a-zA-Z_]\w*\s*\)", "", s)
    s = re.sub(r"\s*&\s*\(\s*[a-zA-Z_]\w*\s*>\s*-oo\s*\)", "", s)
    s = re.sub(r"\s*&\s*\(\s*-oo\s*<\s*[a-zA-Z_]\w*\s*\)", "", s)
    m = re.match(r"^\(([^)]+)\)$", s.strip())
    if m:
        s = m.group(1).strip()

    return s


def _normalize_math_unicode(s: str) -> str:
    """Replace Unicode math characters with ASCII/SymPy equivalents.
    
    Must be called BEFORE any SymPy parsing. Key conversions:
      π → pi (with implicit mult: 2π→2*pi, πn→pi*n)
      √ → sqrt,  ∞ → oo,  − → - (minus sign variants)
    """
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.replace("×", "*").replace("·", "*").replace("÷", "/")
    s = s.replace("≤", "<=").replace("≥", ">=").replace("≠", "!=")
    s = s.replace("∞", "oo")
    s = s.replace("√", "sqrt")
    # π followed by digit: 2π/3 → 2*pi/3  (already caught by later implicit mult rules,
    # but we handle π prefix explicitly to avoid mis-tokenizing)
    s = re.sub(r"(\d)π", r"\1*pi", s)   # 2π → 2*pi
    s = re.sub(r"π([a-zA-Z])", r"pi*\1", s)  # πn → pi*n
    s = s.replace("π", "pi")
    return s


def _normalize_school_expression(s: str) -> str:
    """School LaTeX/unicode → SymPy-parseable (incl. a√a ↔ a**(3/2))."""
    s = (s or "").strip()
    # a\sqrt{b} → a*sqrt(b) before generic sqrt pass
    s = re.sub(r"([a-zA-Z0-9\)])\\sqrt\{([^}]+)\}", r"\1*sqrt(\2)", s)
    s = re.sub(r"([a-zA-Z])√\s*([a-zA-Z])", r"\1*sqrt(\2)", s)
    s = re.sub(r"(\d+)√\s*(\d+)", r"\1*sqrt(\2)", s)
    # Unicode math normalization (π, √, ∞, minus variants)
    s = _normalize_math_unicode(s)
    s = _latexish_to_sympy(s)
    # var*sqrt(var) or sqrt(var)*var → var**(3/2)
    for _ in range(2):
        s = re.sub(r"([a-zA-Z])\*sqrt\(\1\)", r"\1**(3/2)", s, flags=re.I)
        s = re.sub(r"sqrt\(([a-zA-Z])\)\*\1", r"\1**(3/2)", s, flags=re.I)
    return s



def _strip_units(s: str) -> str:
    return re.sub(r"\s*(г|кг|м/с|ч|сек|с)\s*$", "", (s or "").strip(), flags=re.I)


def _normalize_decimal_commas(s: str) -> str:
    """0,15 → 0.15; keep 10^-23 intact."""
    s = (s or "").strip()
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    return s


def _extract_assignments(question: str) -> dict[str, str]:
    """x = -0,37, y = -0,42 or v = 15 from question tail."""
    assigns: dict[str, str] = {}
    for line in (question or "").splitlines():
        if not re.search(r"=\s*[-\d]", line):
            continue
        chunks = re.split(r",\s*(?=[a-zA-Z]\s*=)", line)
        for chunk in chunks:
            m = re.match(r"([a-zA-Z])\s*=\s*(.+)$", chunk.strip().rstrip(";"))
            if m:
                val = _normalize_decimal_commas(m.group(2).strip())
                if val and re.search(r"\d", val):
                    assigns[m.group(1)] = val
        for m in re.finditer(r"[а-я]\)\s*([a-zA-Z])\s*=\s*([^;]+)", line, re.I):
            val = _normalize_decimal_commas(m.group(2).strip())
            if val and re.search(r"\d", val):
                assigns[m.group(1)] = val
    return assigns


def _eval_expr_numeric(expr_str: str, assigns: dict[str, str]) -> Optional[float]:
    """Substitute assignments and evaluate to float."""
    try:
        import sympy
        from sympy import N, Rational

        expr = parse_expr(expr_str)
        if expr is None:
            return None
        subs: dict = {}
        for var, val_s in assigns.items():
            sym = sympy.Symbol(var)
            inner = parse_expr(_normalize_school_expression(val_s))
            if inner is not None:
                subs[sym] = inner
            else:
                try:
                    subs[sym] = float(val_s)
                except ValueError:
                    return None
        val = N(expr.subs(subs))
        if val.is_real:
            return float(val)
    except Exception:
        pass
    return None


def _parse_scientific_value(s: str) -> Optional[float]:
    s = _normalize_school_expression(_strip_units(_normalize_decimal_commas(s)))
    m = re.match(
        r"^([\d.]+)\s*(?:\*|×|·)?\s*10\s*\*\*\s*\(?(-?\d+)\)?$",
        s,
        re.I,
    )
    if not m:
        m = re.match(r"^([\d.]+)\s*(?:\*|×)?\s*10\^\{?(-?\d+)\}?$", s, re.I)
    if m:
        return float(m.group(1)) * (10 ** int(m.group(2)))
    try:
        return float(s)
    except ValueError:
        return None


def _extract_comparison_exprs(question: str) -> tuple[str, str] | None:
    """Two expressions from 'Сравните ... A и B'."""
    q = (question or "").replace("$", "")
    if not re.search(r"сравните", q, re.I):
        return None
    # last line often: expr1 и expr2
    for line in reversed(q.splitlines()):
        line = line.strip().rstrip(";")
        if re.search(r"\sи\s", line, re.I) and re.search(r"[\d\\sqrt]", line, re.I):
            parts = re.split(r"\s+и\s+", line, maxsplit=1, flags=re.I)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
    return None


def _parse_relation(answer: str) -> tuple[str, str, str] | None:
    """lhs rel rhs from answer like 'a > b' or 'a = b'."""
    s = _normalize_school_expression(_strip_units(answer))
    m = re.match(r"^(.+?)\s*(=|<|>|≤|>=|<=|≥)\s*(.+)$", s)
    if not m:
        return None
    rel = m.group(2).replace("≤", "<=").replace("≥", ">=")
    return m.group(1).strip(), rel, m.group(3).strip()


def _relation_holds(lhs: float, rel: str, rhs: float) -> bool:
    if rel == "=":
        return abs(lhs - rhs) < 1e-4
    if rel == "<":
        return lhs < rhs - 1e-9
    if rel == ">":
        return lhs > rhs + 1e-9
    if rel == "<=":
        return lhs <= rhs + 1e-9
    if rel == ">=":
        return lhs >= rhs - 1e-9
    return False


def _fraction_list_parts(s: str) -> list[str]:
    s = (s or "").strip()
    s = re.sub(r"^[:\s]+", "", s)
    parts = re.split(r"\s+и\s+", s, flags=re.I)
    if len(parts) < 2:
        parts = [p.strip() for p in s.split(",") if p.strip()]
    out: list[str] = []
    for p in parts:
        p = re.sub(r"^\d+\)\s*", "", p).strip()
        if p:
            out.append(p)
    return out


def eval_computed_for_question(question: str, computed: str) -> Optional[str]:
    """Numeric value when question gives variable assignments."""
    assigns = _extract_assignments(question)
    if not assigns:
        return None
    if len(re.findall(r"[а-я]\)\s*[a-zA-Z]\s*=", question or "", re.I)) >= 2:
        return None
    val = _eval_expr_numeric(computed, assigns)
    if val is None:
        return None
    if abs(val - round(val)) < 1e-6:
        return str(int(round(val)))
    return str(round(val, 6)).rstrip("0").rstrip(".")


def _parse_mixed_number(s: str) -> Optional[float]:
    s = (s or "").strip()
    m = re.match(r"^(\d+)\s+(\d+)/(\d+)$", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    try:
        from fractions import Fraction

        return float(Fraction(_normalize_school_expression(s)))
    except Exception:
        return None


def _validate_formula_with_cases(question: str, answer: str, formula_expr: str) -> bool:
    """Formula + а) v=… numeric parts — e.g. t = 30/v + 17/(v+2); а) 3; б) 2 31/60."""
    parts = split_answer_parts(answer)
    if len(parts) < 2:
        return False
    formula_part = parts[0].strip()
    fm = re.match(r"^([a-zA-Z])\s*=\s*(.+)$", formula_part)
    rhs = fm.group(2).strip() if fm else formula_part
    if sympy_equivalent(rhs, formula_expr, "expression") is not True:
        if sympy_equivalent(formula_expr, rhs, "expression") is not True:
            return False
    case_parts = parts[1:]
    case_specs = re.findall(r"[а-я]\)\s*([a-zA-Z])\s*=\s*([^;]+)", question, re.I)
    if len(case_specs) != len(case_parts):
        return False
    for (var, val_s), part in zip(case_specs, case_parts):
        assigns = {var: _normalize_decimal_commas(val_s.strip())}
        got = _eval_expr_numeric(formula_expr, assigns)
        if got is None:
            return False
        part_clean = re.sub(r"\s*ч\s*$", "", part.strip(), flags=re.I)
        exp = _parse_mixed_number(part_clean) or _parse_mixed_number(
            _normalize_decimal_commas(part_clean)
        )
        if exp is None:
            try:
                exp = float(_normalize_decimal_commas(part_clean))
            except ValueError:
                return False
        if abs(got - exp) > 0.02:
            return False
    return True


@timeout_default(5, default_val=None)
def try_validate_expression_answer(question: str, answer: str) -> Optional[bool]:
    """Validate expression answer against question (substitution, compare, numeric)."""
    q = (question or "").strip()
    ans = _normalize_decimal_commas(_strip_units((answer or "").strip()))
    if not q or not ans:
        return None

    # Constraint n < 0: |n| vs -n
    if re.search(r"n\s*<\s*0", q, re.I):
        ea, eb = parse_expr(ans), parse_expr("Abs(n)")
        if ea is not None and eb is not None:
            try:
                import sympy
                from sympy import N

                n = sympy.Symbol("n")
                if abs(float(N(ea.subs(n, -3))) - float(N(eb.subs(n, -3)))) < 1e-6:
                    return True
            except Exception:
                pass

    # Comparison: sqrt(24) = 1/3*sqrt(216)
    pair = _extract_comparison_exprs(q)
    rel = _parse_relation(ans)
    if pair and rel:
        lhs_a, op, rhs_a = rel
        v1 = _eval_expr_numeric(lhs_a, {}) if not _extract_assignments(q) else None
        # numeric eval both sides of relation
        try:
            import sympy
            from sympy import N

            e1, e2 = parse_expr(lhs_a), parse_expr(rhs_a)
            if e1 is not None and e2 is not None:
                f1, f2 = float(N(e1)), float(N(e2))
                return _relation_holds(f1, op, f2)
        except Exception:
            pass

    # Scientific notation
    sci = _parse_scientific_value(ans)
    if sci is not None and re.search(r"10\s*\^", q):
        m_mol = re.search(r"([\d.,]+)\s*\*\s*10\s*\^?\s*(\d+)", q.replace(" ", ""))
        m_g = re.search(r"(\d+)\s*г", q)
        if m_mol and m_g:
            molecules = float(m_mol.group(1).replace(",", ".")) * (10 ** int(m_mol.group(2)))
            mass = float(m_g.group(1))
            expected = mass / molecules
            if abs(sci - expected) / max(abs(expected), 1e-30) < 0.02:
                return True

    # Substitution numeric answer — validated via eval_computed_for_question in gate
    assigns = _extract_assignments(q)
    if assigns and re.search(r"^[-\d.]", ans):
        return None

    # Formula + labeled numeric cases: t = …; а) 3; б) 2 31/60
    if re.search(r"[а-я]\)\s*[a-zA-Z]\s*=", q, re.I) and ";" in ans:
        parts = split_answer_parts(ans)
        if len(parts) >= 2:
            fm = re.match(r"^([a-zA-Z])\s*=\s*(.+)$", parts[0].strip())
            if fm and _validate_formula_with_cases(q, ans, fm.group(2)):
                return True

    # Fraction list: 10/14 и 3/14
    fracs = _fraction_list_parts(ans)
    if len(fracs) >= 2 and re.search(r"знаменател", q, re.I):
        try:
            from fractions import Fraction

            got = [Fraction(_normalize_school_expression(f)) for f in fracs]
            # from question line 5/7 и 3/14
            for line in q.splitlines():
                if " и " in line and "/" in line:
                    src = _fraction_list_parts(line)
                    if len(src) == len(got):
                        exp = [Fraction(_normalize_school_expression(f)) for f in src]
                        # allow non-reduced vs reduced
                        if len(got) == len(exp) and all(
                            a == b or float(a) == float(b) for a, b in zip(sorted(got, key=float), sorted(exp, key=float))
                        ):
                            return True
        except Exception:
            pass

    return try_validate_answer_for_question(q, ans, "expression")


def split_answer_parts(answer: str) -> list[str]:
    """Split multi-part answers (а) б) в); ...; or comma-separated fractions)."""
    s = (answer or "").strip()
    if not s:
        return []

    def _clean(parts: list[str]) -> list[str]:
        cleaned: list[str] = []
        for p in parts:
            p = re.sub(r"^[абвгдежзийклмнопрстуфхцчшщъыьэюя]\)\s*", "", p, flags=re.I)
            p = re.sub(r"^\d+\)\s*", "", p)
            p = p.strip()
            if p:
                cleaned.append(p)
        return cleaned

    if ";" in s:
        parts = []
        depth = 0
        curr = []
        for ch in s:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            
            if ch == ";" and depth == 0:
                parts.append("".join(curr))
                curr = []
            else:
                curr.append(ch)
        if curr:
            parts.append("".join(curr))
        
        parts = _clean(parts)
        if len(parts) >= 2:
            return parts

    if "," in s:
        # Split by comma outside parentheses
        parts = []
        depth = 0
        curr = []
        for ch in s:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            
            if ch == "," and depth == 0:
                parts.append("".join(curr))
                curr = []
            else:
                curr.append(ch)
        if curr:
            parts.append("".join(curr))
            
        cand = _clean(parts)
        if len(cand) >= 2 and all(
            re.search(r"[=/^()]|[a-zA-Z]", p) for p in cand
        ):
            return cand

    parts = _clean([s])
    return parts if parts else [s]


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

    raw = _normalize_school_expression(expr_str)
    if not raw:
        return None

    # Handle top-level equation equality: x = y -> Eq(x, y)
    eq_idx = -1
    if "=" in raw:
        depth = 0
        eq_count = 0
        for i, char in enumerate(raw):
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            elif char == "=" and depth == 0:
                eq_count += 1
                eq_idx = i
        if eq_count != 1:
            eq_idx = -1

    if eq_idx != -1:
        lhs_part = raw[:eq_idx].strip()
        rhs_part = raw[eq_idx + 1:].strip()
        lhs = parse_expr(lhs_part)
        rhs = parse_expr(rhs_part)
        if lhs is not None and rhs is not None:
            from sympy import Eq
            return Eq(lhs, rhs)

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
        if safe_simplify(a - b) == 0:
            return True
    except Exception:
        pass
    try:
        if sympy.Eq(safe_simplify(a), safe_simplify(b)):
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


def _standardize_math_tuple(s: str) -> list[str] | None:
    s = (s or "").strip()
    m = re.match(r"^\((.+)\)$", s)
    if m:
        s = m.group(1).strip()
    
    parts = [p.strip() for p in re.split(r"[;,]", s) if p.strip()]
    eqs = {}
    for p in parts:
        eq_match = re.match(r"^([a-zA-Z_]\w*)\s*(=|!=|≠)\s*(.+)$", p)
        if eq_match:
            eqs[eq_match.group(1)] = eq_match.group(3).strip()
    if eqs:
        sorted_keys = sorted(eqs.keys())
        return [eqs[k] for k in sorted_keys]
        
    if ";" in s:
        return [p.strip() for p in s.split(";") if p.strip()]
    if "," in s:
        cand = [p.strip() for p in s.split(",") if p.strip()]
        if len(cand) >= 2 and not all(re.fullmatch(r"\d+", p) for p in cand):
            return cand
            
    return None


def _parse_scalar_numeric(s: str):
    """Parse a single math expression to a complex number, or None.
    
    Uses sympy.N() for evaluation. Returns None on failure.
    Designed to handle trig constants: pi/2, -3*pi/2, sqrt(2), etc.
    """
    s = s.strip()
    if not s:
        return None
    try:
        import sympy
        from sympy.parsing.sympy_parser import (
            implicit_multiplication_application,
            parse_expr as sympy_parse_expr,
            standard_transformations,
        )
        transformations = standard_transformations + (implicit_multiplication_application,)
        expr = sympy_parse_expr(s, transformations=transformations)
        return complex(sympy.N(expr, 15))
    except Exception:
        return None


def _numeric_multiset_compare(a: str, b: str) -> Optional[bool]:
    """Fast numeric comparison for comma/semicolon-separated math values.
    
    Compares sets of numbers (including trig constants) by evaluating them
    numerically. Safe against trig expressions — never calls solve() or as_set().
    
    Returns True if same multiset numerically, False if different sizes or values,
    None if parsing fails (fallback to symbolic comparison).
    
    Examples handled correctly:
      '-3pi/2, -pi/2, pi/2, 5pi/2'  vs  '-3*pi/2; -pi/2; pi/2; 5*pi/2'  → True
      '{pi/2, 0, -pi, 2*pi}'         vs  '{0, pi/2, -pi, 2*pi}'           → True
      'pi/2'                          vs  'pi/2'                            → True
    """
    def to_numeric_values(s: str):
        # Strip set/tuple braces
        s = re.sub(r"^[{(\[]\s*|\s*[})\]]$", "", s.strip())
        # Split on ; or ,
        parts = [p.strip() for p in re.split(r"[;,]", s) if p.strip()]
        if not parts:
            return None
        values = []
        for p in parts:
            v = _parse_scalar_numeric(p)
            if v is None:
                return None
            values.append(v)
        return sorted(values, key=lambda x: (x.real, x.imag))

    va = to_numeric_values(a)
    vb = to_numeric_values(b)
    if va is None or vb is None:
        return None
    if len(va) != len(vb):
        return False
    return all(abs(x - y) < 1e-6 for x, y in zip(va, vb))


@timeout_default(5, default_val=None)
def sympy_equivalent(a: str, b: str, answer_type: str = "") -> Optional[bool]:
    """
    True = mathematically same, False = different, None = cannot decide.

    Strategy order (fast → slow, bailing early):
      1. String equality after unicode normalization
      2. Numeric multi-set comparison (handles π/∞ sets, trig values)
      3. SymPy parse + direct equality / simplification
      4. Monte-Carlo random substitution
    Deliberately avoids as_set() / solve() to prevent hangs on trig expressions.
    """
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return None
    # Strategy 1: normalized string equality
    a_norm = _normalize_math_unicode(a)
    b_norm = _normalize_math_unicode(b)
    if a_norm == b_norm:
        return True
    if a == b:
        return True

    # Strategy 2: fast numeric multi-set comparison
    # Handles: 'π/2', 'pi/2'; '-3π/2,-π/2,π/2', '-3*pi/2;-pi/2;pi/2'
    # No symbolic solving, just N() evaluation — safe and fast
    numeric_result = _numeric_multiset_compare(a_norm, b_norm)
    if numeric_result is not None:
        return numeric_result

    # Strategy 3: Try tuple/part standardization
    ta = _standardize_math_tuple(a)
    tb = _standardize_math_tuple(b)
    if ta is not None and tb is not None and len(ta) == len(tb) and len(ta) > 0:
        results = [sympy_equivalent(x, y, answer_type) for x, y in zip(ta, tb)]
        if all(r is True for r in results):
            return True

    pa, pb = split_answer_parts(a), split_answer_parts(b)
    if len(pa) == len(pb) and len(pa) > 1:
        matched_indices = set()
        for x in pa:
            found = False
            for idx, y in enumerate(pb):
                if idx not in matched_indices and sympy_equivalent(x, y, answer_type):
                    matched_indices.add(idx)
                    found = True
                    break
            if not found:
                break
        if len(matched_indices) == len(pb):
            return True
        return None

    # Strategy 4: SymPy symbolic parse (skip as_set() — hangs on trig)
    ea, eb = parse_expr(a), parse_expr(b)
    if ea is not None and eb is not None:
        try:
            from sympy import nsimplify
            ea = nsimplify(ea)
            eb = nsimplify(eb)
        except Exception:
            pass

        if ea == eb:
            import sympy
            if isinstance(ea, (sympy.logic.boolalg.BooleanAtom, bool)):
                if _normalize_math_unicode(a).replace(" ", "") != _normalize_math_unicode(b).replace(" ", ""):
                    return False
            return True

        # NOTE: deliberately omitting ea.as_set() == eb.as_set()
        # as it calls sympy.solve() internally and hangs on trig expressions.

        if _exprs_equivalent(ea, eb):
            return True
        mc = monte_carlo_equivalent(a, b)
        if mc is not None:
            return mc
        return False

    # Strategy 5: Monte-Carlo only
    mc = monte_carlo_equivalent(a, b)
    if mc is not None:
        return mc
    return None


@timeout_default(5, default_val=None)
def sympy_numeric_equal(a: str, b: str) -> Optional[bool]:
    ea, eb = parse_expr(a), parse_expr(b)
    if ea is None or eb is None:
        return None
    try:
        from sympy import N

        return abs(float(N(ea)) - float(N(eb))) < 1e-6
    except Exception:
        return None


@timeout_default(5, default_val=None)
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

        simplified = safe_simplify(target)
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


@timeout_default(5, default_val=None)
def back_substitute_roots(question: str, answer: str, answer_type: str) -> Optional[bool]:
    """
    Strategy 2 SymPy proof: extract equation from question text, substitute roots back in.

    Returns:
      True   — all roots satisfy the equation (mathematically proven)
      False  — at least one root does NOT satisfy the equation (proven wrong)
      None   — cannot verify algebraically (symbolic, text task, multi-variable, etc.)

    Applicable to: equation_solution, set, exact_number, decimal, fraction.
    """
    import re

    at = (answer_type or "").lower()
    if at not in ("equation_solution", "set", "exact_number", "decimal", "fraction"):
        return None

    q = (question or "").strip()
    ans = (answer or "").strip()
    if not q or not ans:
        return None

    # ── Step 1: Find candidate equation lines in the question ──────────────
    eq_lines = []
    for line in q.splitlines():
        line = line.strip()
        if "=" in line and re.search(r"[0-9a-zA-Z\^]\s*=", line):
            # Skip meta-hints: "Ответ:", "= ?", "нет данных"
            if not re.search(r"[Оо]твет|=\s*\?|ОТВЕТ|нет\s*данных", line):
                eq_lines.append(line)
    if not eq_lines:
        return None

    # ── Step 2: Parse answer into numeric roots ─────────────────────────────
    # Must be parenthesis-aware split: '3 - sqrt(5); 3 + sqrt(5)' must not split inside ()
    def _paren_split(text: str) -> list:
        parts, current, depth = [], [], 0
        for ch in text:
            if ch in "([":
                depth += 1
                current.append(ch)
            elif ch in ")]":
                depth -= 1
                current.append(ch)
            elif ch in ";," and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current).strip())
        return [p for p in parts if p]

    try:
        import sympy
        from src.pipeline.answer_sympy import _latexish_to_sympy as _lts

        roots = []
        for p in _paren_split(ans):
            p = p.strip().replace("x=", "").replace("y=", "").strip()
            # Strip only OUTER matching parens (coordinate wrapper), not function parens
            if p.startswith("(") and p.endswith(")"):
                inner = p[1:-1]
                if inner.count("(") == inner.count(")"):
                    p = inner.strip()
            try:
                sym_p = _lts(p)
                if sym_p:
                    val_num = complex(sympy.N(sympy.sympify(sym_p)))
                    roots.append(val_num)
            except Exception:
                pass
        if not roots:
            return None

        # ── Step 3: Try each equation line ────────────────────────────────────
        for eq_line in eq_lines[:3]:
            eq_raw = re.sub(r"^[абвгдежзийклмнопрстуфхцч]\)\.?\s*", "", eq_line, flags=re.I)
            eq_raw = re.sub(r"\\[\(\)]", "", eq_raw).replace("$", "").strip()

            eq_sides = eq_raw.split("=")
            if len(eq_sides) != 2:
                continue
            lhs_raw, rhs_raw = eq_sides

            try:
                lhs_sym = _lts(lhs_raw.strip())
                rhs_sym = _lts(rhs_raw.strip())
                if lhs_sym is None:
                    continue

                lhs_expr = sympy.sympify(lhs_sym)
                rhs_expr = sympy.sympify(rhs_sym) if rhs_sym else sympy.Integer(0)
                diff_expr = sympy.expand(lhs_expr - rhs_expr)
                free_vars = diff_expr.free_symbols

                # Only verify single-variable equations
                if not free_vars or len(free_vars) > 1:
                    continue
                var = sorted(free_vars, key=lambda s: str(s))[0]

                proofs = []
                for root in roots:
                    try:
                        val_at_root = complex(sympy.N(diff_expr.subs(var, root)))
                        proofs.append(abs(val_at_root) < 1e-4)
                    except Exception:
                        proofs.append(None)

                if all(p is True for p in proofs):
                    return True
                if any(p is False for p in proofs):
                    return False
            except Exception:
                continue

    except Exception as e:
        log.debug("back_substitute_roots error: %s", e)

    return None
