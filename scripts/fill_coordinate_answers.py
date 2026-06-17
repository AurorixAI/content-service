r"""
Таргетированный скрипт: решает G7 системы уравнений (coordinate type) через SymPy.

Парсит LaTeX \begin{cases}...\end{cases} и inline форматы,
решает через sympy.solve, сохраняет ответ в формате "(x; y)".

Особые случаи:
  - нет решения           -> "нет решения"
  - бесконечно много      -> "бесконечно много решений"
"""
from __future__ import annotations

import json
import logging
import re
import sys
from typing import Optional

sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fill_coord")

try:
    import sympy as sp
    from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
except ImportError:
    log.error("sympy not available")
    sys.exit(1)

from sqlalchemy import create_engine, text
from src.core.config import get_settings


# ── Equation parser ────────────────────────────────────────────────────────────

def _clean_latex_eq(eq: str) -> str:
    """Strip LaTeX artifacts and normalise equation string."""
    eq = eq.strip()
    eq = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", eq)  # \frac{a}{b} → a/b (approx)
    eq = eq.replace("\\\\", "").replace("\\", "")
    eq = eq.replace("·", "*").replace("×", "*")
    # LaTeX fractions: \frac{a}{b} → (a)/(b)
    eq = re.sub(r"frac\{([^}]+)\}\{([^}]+)\}", r"(\1)/(\2)", eq)
    eq = eq.strip(". ")
    return eq


def _parse_cases_latex(text_block: str) -> list[str]:
    r"""Extract equations from \begin{cases}...\end{cases}."""
    m = re.search(r"\\begin\{cases\}(.*?)\\end\{cases\}", text_block, re.DOTALL)
    if m:
        inner = m.group(1)
        parts = re.split(r"\\\\", inner)
        return [_clean_latex_eq(p) for p in parts if p.strip()]
    return []


def _parse_inline_eqs(text_block: str) -> list[str]:
    """Parse comma-separated equations like '-5x + 4y = -16, x + 4y = 8'."""
    candidates = []
    for line in re.split(r"[,\n]", text_block):
        line = line.strip()
        if "=" in line and re.search(r"[xy]", line):
            candidates.append(_clean_latex_eq(line))
    return candidates


def _extract_equations(question_text: str) -> list[str]:
    """Try cases LaTeX first, then inline."""
    eqs = _parse_cases_latex(question_text)
    if not eqs:
        eqs = _parse_inline_eqs(question_text)
    return eqs


def _solve_system(eq_strs: list[str]) -> Optional[str]:
    """
    Solve 2x2 linear system.
    Returns formatted string "(x_val; y_val)", "нет решения", or None on parse error.
    """
    if len(eq_strs) < 2:
        return None

    x, y = sp.symbols("x y")
    transformations = standard_transformations + (implicit_multiplication_application,)

    equations = []
    for eq_str in eq_strs[:2]:
        parts = eq_str.split("=", 1)
        if len(parts) != 2:
            return None
        try:
            lhs = parse_expr(parts[0].strip(), transformations=transformations, local_dict={"x": x, "y": y})
            rhs = parse_expr(parts[1].strip(), transformations=transformations, local_dict={"x": x, "y": y})
            equations.append(sp.Eq(lhs, rhs))
        except Exception as e:
            log.debug("Parse error for '%s': %s", eq_str, e)
            return None

    try:
        sol = sp.solve(equations, [x, y], dict=True)
    except Exception as e:
        log.debug("SymPy solve error: %s", e)
        return None

    if not sol:
        # Check if inconsistent (no solution) vs underdetermined
        try:
            aug = sp.Matrix([[eq.lhs.coeff(x), eq.lhs.coeff(y), eq.rhs]
                             for eq in equations])
        except Exception:
            return "нет решения"
        return "нет решения"

    if isinstance(sol, list):
        if len(sol) == 0:
            return "нет решения"
        sol_dict = sol[0]
        # Check for free variables (infinite solutions)
        if any(isinstance(v, sp.Symbol) for v in sol_dict.values()):
            return "бесконечно много решений"
        x_val = sol_dict.get(x)
        y_val = sol_dict.get(y)
    elif isinstance(sol, dict):
        if any(isinstance(v, sp.Symbol) for v in sol.values()):
            return "бесконечно много решений"
        x_val = sol.get(x)
        y_val = sol.get(y)
    else:
        return None

    if x_val is None or y_val is None:
        return None

    def _fmt(val) -> str:
        # val comes directly from SymPy solve — keep as exact Rational
        v = sp.nsimplify(val, rational=True)
        if isinstance(v, sp.Integer) or (hasattr(v, "is_integer") and v.is_integer):
            return str(int(v))
        if isinstance(v, sp.Rational):
            return f"{v.p}/{v.q}"
        # Fallback: round to 4 significant digits
        return str(round(float(v), 4))

    try:
        xs = _fmt(x_val)
        ys = _fmt(y_val)
        return f"({xs}; {ys})"
    except Exception:
        return f"({x_val}; {y_val})"


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    cfg = get_settings()
    engine = create_engine(cfg.database_url)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT tm.id, tm.question_text
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = 7
              AND tm.answer_type = 'coordinate'
              AND (tm.correct_answer = '' OR tm.correct_answer IS NULL)
            ORDER BY tm.id
        """)).fetchall()

    log.info("Found %d coordinate tasks without answers", len(rows))

    solved = 0
    no_solution = 0
    failed = 0

    for task_id, question_text in rows:
        eqs = _extract_equations(question_text or "")
        if not eqs:
            log.warning("SKIP %s — could not parse equations", task_id)
            failed += 1
            continue

        answer = _solve_system(eqs)
        if answer is None:
            log.warning("SKIP %s — SymPy could not solve: %s", task_id, eqs)
            failed += 1
            continue

        with engine.begin() as conn:
            conn.execute(
                text("UPDATE tasks_master SET correct_answer = :ans WHERE id = :id"),
                {"ans": answer, "id": task_id},
            )

        if answer in ("нет решения", "бесконечно много решений"):
            log.info("  %s → %s", task_id, answer)
            no_solution += 1
        else:
            log.info("  %s → %s", task_id, answer)
            solved += 1

    log.info(
        "Done: %d solved, %d special answers (no/infinite solution), %d failed",
        solved, no_solution, failed,
    )


if __name__ == "__main__":
    main()
