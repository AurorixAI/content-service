"""Local SymPy gate for Smart Verify (evaluate LLM sympy_compatible_string)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from src.pipeline.answer_sympy import _latexish_to_sympy, parse_expr, sympy_equivalent

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


def _sympy_namespace() -> dict[str, Any]:
    import sympy
    from sympy import Eq, Ne, Le, Ge, Lt, Gt, solve, symbols, simplify, sqrt, pi, E

    x, y, z, n, a, b, c, t = symbols("x y z n a b c t")
    return {
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


def _format_sympy_result(result: Any, answer_type: str) -> Optional[str]:
    import sympy
    from sympy import Eq

    at = (answer_type or "").lower()

    if isinstance(result, Eq):
        try:
            sols = sympy.solve(result)
            return _format_solutions(sols, at)
        except Exception:
            return None

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


def _format_solutions(sols: Any, answer_type: str) -> Optional[str]:
    import sympy

    if sols is None:
        return None
    if isinstance(sols, dict):
        parts = []
        for k in sorted(sols.keys(), key=str):
            v = sols[k]
            parts.append(f"{k}={v}")
        return "; ".join(parts) if parts else None
    if isinstance(sols, (list, tuple, set)):
        if not sols:
            return "нет корней"
        flat: list[str] = []
        for s in sols:
            if isinstance(s, dict):
                sub = _format_solutions(s, answer_type)
                if sub:
                    flat.append(sub)
            else:
                try:
                    from sympy import N

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

    # solve(Eq(...), x) → take solutions
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

    # Python-like Eq(...) form from LLM
    if raw.startswith("Eq(") or raw.startswith("Ne("):
        try:
            return eval(raw, {"__builtins__": {}}, ns)  # noqa: S307
        except Exception:
            pass

    converted = _latexish_to_sympy(raw)
    try:
        return sympify(converted, locals=ns)
    except Exception:
        pass

    expr = parse_expr(converted)
    if expr is not None:
        return expr

    raise ValueError(f"cannot parse sympy_compatible_string: {raw[:80]!r}")


def evaluate_sympy_string(sympy_string: str, answer_type: str) -> Optional[str]:
    """
    Evaluate LLM sympy_compatible_string locally → canonical answer string.
    Returns None if evaluation fails.
    """
    try:
        obj = _parse_sympy_compatible_string(sympy_string)
    except Exception as exc:
        log.debug("evaluate_sympy_string parse failed: %s", exc)
        return None

    at = (answer_type or "").lower()

    # If it's an equation, solve it
    import sympy
    from sympy import Eq

    if isinstance(obj, Eq):
        try:
            sols = sympy.solve(obj)
            return _format_solutions(sols, at)
        except Exception as exc:
            log.debug("solve Eq failed: %s", exc)
            return None

    # Expression types: simplify
    if at in ("expression", "fraction"):
        try:
            simplified = sympy.simplify(obj)
            return str(simplified)
        except Exception:
            return _format_sympy_result(obj, at)

    return _format_sympy_result(obj, at)


@dataclass
class SympyGateResult:
    ok: bool
    computed_local: Optional[str] = None
    reason: str = ""


def _try_validate_equation_answer(question: str, answer: str) -> Optional[bool]:
    """Solve equation from question text and compare to answer."""
    q = (question or "").strip()
    ans = (answer or "").strip()
    if not q or not ans:
        return None

    try:
        import sympy
        from sympy import Eq, solve, symbols
        from sympy.parsing.sympy_parser import (
            implicit_multiplication_application,
            parse_expr,
            standard_transformations,
        )
    except ImportError:
        return None

    transformations = standard_transformations + (implicit_multiplication_application,)
    x = symbols("x")

    for line in reversed(q.splitlines()):
        line = line.strip()
        if "=" not in line or not re.search(r"[0-9]", line):
            continue
        cleaned = _latexish_to_sympy(line)
        if "=" not in cleaned:
            continue
        lhs_s, rhs_s = cleaned.split("=", 1)
        try:
            l_expr = parse_expr(lhs_s.strip(), transformations=transformations)
            r_expr = parse_expr(rhs_s.strip(), transformations=transformations)
            eq = Eq(l_expr, r_expr)
            syms = list(eq.free_symbols)
            if not syms:
                continue
            sols = solve(eq, syms[0])
            expected = _format_solutions(sols, "equation_solution")
            if expected is None:
                continue
            equiv = sympy_equivalent(expected, ans, "equation_solution")
            if equiv is not None:
                return equiv
        except Exception:
            continue
    return None


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
    from src.pipeline.answer_verify import answers_equivalent
    from src.pipeline.answer_sympy import try_validate_answer_for_question

    absolute_answer = (absolute_answer or "").strip()
    stored_answer = (stored_answer or "").strip()
    if not absolute_answer:
        return SympyGateResult(ok=False, reason="empty_absolute_answer")

    computed = evaluate_sympy_string(sympy_string, answer_type)
    if computed is not None:
        equiv = sympy_equivalent(computed, absolute_answer, answer_type)
        if equiv is True:
            return SympyGateResult(ok=True, computed_local=computed, reason="sympy_match")
        if equiv is False:
            return SympyGateResult(
                ok=False,
                computed_local=computed,
                reason=f"local_mismatch: {computed!r} vs {absolute_answer!r}",
            )

    # Soft gate: validate answer against question when sympy_string parse fails
    q_valid = try_validate_answer_for_question(question, absolute_answer, answer_type)
    if q_valid is True:
        return SympyGateResult(
            ok=True,
            computed_local=computed,
            reason="question_validated_fallback",
        )

    if (answer_type or "").lower() == "equation_solution":
        eq_valid = _try_validate_equation_answer(question, absolute_answer)
        if eq_valid is True:
            return SympyGateResult(
                ok=True,
                computed_local=computed,
                reason="equation_solved_fallback",
            )
        if eq_valid is False:
            return SympyGateResult(
                ok=False,
                computed_local=computed,
                reason="equation_mismatch_fallback",
            )

    if computed is None:
        # Textbook confirms code-execution output (common for equation tasks)
        if stored_answer and answers_equivalent(stored_answer, absolute_answer, answer_type):
            return SympyGateResult(
                ok=True,
                computed_local=absolute_answer,
                reason="textbook_agrees_with_llm",
            )
        return SympyGateResult(ok=False, reason="eval_failed")

    # Fallback: normalized string compare
    a = re.sub(r"\s+", "", (computed or "").lower())
    b = re.sub(r"\s+", "", absolute_answer.lower())
    if a == b:
        return SympyGateResult(ok=True, computed_local=computed, reason="string_match")

    return SympyGateResult(
        ok=False,
        computed_local=computed,
        reason="undecidable_equivalence",
    )
