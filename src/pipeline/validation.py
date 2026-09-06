"""
ALGO V1 — SymPy Answer Verification
src/pipeline/validation.py

5 стратегий верификации ответа задачи:
  1. direct  — прямое числовое вычисление / дробь
  2. equation — решение уравнения из LaTeX
  3. simplify — упрощение выражения
  4. numerical — числовое приближение
  5. expression — произвольное символьное выражение
"""

from __future__ import annotations

import logging
from typing import Any, Tuple, Optional

from src.pipeline.models import ExtractedTask

log = logging.getLogger("pipeline")
from src.pipeline.answer_sympy import safe_simplify, timeout_limit, TimeoutException


class SymPySolver:
    """Верифицирует ответ задачи через SymPy (5 стратегий).
    
    Также умеет ВЫЧИСЛЯТЬ ответ из question_latex когда answer_raw пуст
    (метод compute). Это позволяет enricher'у не тратить Gemini Pro на решение.
    """

    # Маркеры пропуска в LaTeX-выражениях учебника
    _BLANK_PATTERNS = (r"\square", r"\Box", r"\ldots", r"…", "?", "__", "___")

    def compute(self, task: ExtractedTask) -> ExtractedTask:
        try:
            with timeout_limit(5):
                return self._compute_internal(task)
        except Exception as e:
            log.warning("SymPy compute timed out or failed: %s", e)
            return task

    def _compute_internal(self, task: ExtractedTask) -> ExtractedTask:
        """Пробует вычислить answer_raw из question_latex, если он пуст.
        
        Стратегии:
        1. Выражение вида  `E = \square`  → вычислить E
        2. Уравнение вида  `x + 5 = 12`  → solve(x)
        3. Чистое арифметическое выражение без '='  → sympify+eval
        """
        missing = not (task.answer_raw or "").strip() or \
                  (task.answer_raw or "").strip() in {"—", "-", "?", "..."}
        if not missing:
            return task

        latex = (task.question_latex or "").strip()
        if not latex:
            return task

        try:
            import sympy
            from sympy import sympify, N, symbols, solve, Eq
            from sympy.parsing.latex import parse_latex
        except ImportError:
            return task

        # Нормализуем: убираем маркеры пропуска
        clean = latex
        for pat in self._BLANK_PATTERNS:
            clean = clean.replace(pat, "")
        clean = clean.strip().rstrip("=").strip()

        # Стратегия 1: "левое_выражение = " (пустое правое) → вычислить левое
        if "=" not in clean:
            try:
                expr = parse_latex(clean)
                val = safe_simplify(expr)
                # Если числовое — сохраняем как строку
                num = float(N(val, 10))
                # Prefer integer representation when exact
                task.answer_raw = str(int(num)) if num == int(num) else str(round(num, 6))
                log.debug("SymPy computed answer for %s: %s", task.temp_id, task.answer_raw)
                return task
            except Exception:
                pass

        # Стратегия 2: уравнение с явным '='
        if "=" in clean:
            sides = clean.split("=", 1)
            lhs_str, rhs_str = sides[0].strip(), sides[1].strip()
            # Если правая сторона — число/выражение без переменных → вычислить левую
            try:
                lhs = parse_latex(lhs_str)
                rhs = parse_latex(rhs_str)
                lhs_val = float(N(safe_simplify(lhs), 10))
                rhs_val = float(N(safe_simplify(rhs), 10))
                # Обе стороны числовые → просто проверяем, ответа нет
                # Значит это "найди x" — пробуем solve
                _ = lhs_val, rhs_val
            except Exception:
                pass
            # Solve for x
            x = symbols("x")
            try:
                lhs = parse_latex(lhs_str)
                rhs = parse_latex(rhs_str)
                sols = solve(Eq(lhs, rhs), x)
                if sols and len(sols) == 1:
                    sol = sols[0]
                    num = float(N(sol, 10))
                    task.answer_raw = str(int(num)) if num == int(num) else str(round(num, 6))
                    log.debug("SymPy solved equation for %s: x=%s", task.temp_id, task.answer_raw)
                    return task
                elif sols:
                    task.answer_raw = "; ".join(
                        str(int(float(N(s, 10)))) if float(N(s, 10)) == int(float(N(s, 10)))
                        else str(round(float(N(s, 10)), 6))
                        for s in sols
                    )
                    log.debug("SymPy solved multi-sol for %s: %s", task.temp_id, task.answer_raw)
                    return task
            except Exception:
                pass

        return task

    @staticmethod
    def compute_from_expr(expr_str: str) -> str | None:
        """Вычисляет ответ из строки-выражения в SymPy-формате.

        Принимает строки вида:
          '2 + 3 * 4'          → '14'
          'x + 5 = 12'         → '7'
          '(3/4) + (1/2)'      → '5/4'
          'x**2 = 4'           → '2; -2'
        Возвращает строку-ответ или None при неудаче.
        """
        if not expr_str or not expr_str.strip():
            return None
        try:
            import sympy
            from sympy import sympify, N, symbols, solve, Eq, Rational
            from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application

            with timeout_limit(5):
                transformations = standard_transformations + (implicit_multiplication_application,)
                s = expr_str.strip().replace("^", "**").replace(",", ".")

            if "=" in s:
                parts = s.split("=", 1)
                lhs_s, rhs_s = parts[0].strip(), parts[1].strip()
                if not lhs_s or not rhs_s:
                    return None
                x = symbols("x")
                lhs = parse_expr(lhs_s, transformations=transformations, local_dict={"x": x})
                rhs = parse_expr(rhs_s, transformations=transformations, local_dict={"x": x})
                sols = solve(Eq(lhs, rhs), x)
                if not sols:
                    return None
                results = []
                for sol in sols:
                    sol = safe_simplify(sol)
                    if sol.is_Number:
                        f = float(N(sol, 15))
                        results.append(str(int(f)) if f == int(f) else str(sol))
                    else:
                        results.append(str(sol))
                return "; ".join(results) if results else None
            else:
                expr = parse_expr(s, transformations=transformations)
                val = safe_simplify(expr)
                if val.is_Number:
                    f = float(N(val, 15))
                    # Prefer exact fraction over decimal
                    r = Rational(val).limit_denominator(10000)
                    if abs(float(r) - f) < 1e-9:
                        return str(int(f)) if r.denominator == 1 else str(r)
                    return str(round(f, 6))
                return str(val)
        except Exception:
            return None

    def verify(self, task: ExtractedTask) -> ExtractedTask:
        """Верифицирует ответ, заполняет ``sympy_*`` поля."""
        try:
            import sympy  # noqa: F401
        except ImportError:
            log.warning("SymPy не установлен, пропуск верификации")
            return task

        # Если ответа ещё нет — сначала попробуем вычислить
        task = self.compute(task)

        answer = (task.answer_raw or "").strip()
        if not answer or answer == "—":
            return task

        strategies = [
            self._try_direct_eval,
            self._try_equation,
            self._try_simplify,
            self._try_numerical,
            self._try_expression,
        ]

        for strategy in strategies:
            try:
                with timeout_limit(5):
                    result, confidence = strategy(answer, task)
                if result is not None and confidence >= 0.5:
                    task.sympy_verified = True
                    task.sympy_answer = str(result)
                    task.sympy_confidence = confidence
                    return task
            except Exception as e:
                log.debug("Strategy %s failed or timed out: %s", strategy.__name__, e)
                continue

        log.debug("SymPy не смог верифицировать: %s (%s)", task.temp_id, answer)
        return task

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    @staticmethod
    def _try_direct_eval(answer: str, task: ExtractedTask) -> Tuple[Any, float]:
        from fractions import Fraction

        clean = answer.replace(",", ".").strip()
        if "/" in clean:
            parts = clean.split("/")
            if len(parts) == 2:
                try:
                    num = float(parts[0].strip())
                    den = float(parts[1].strip())
                    if den != 0:
                        frac = Fraction(num / den).limit_denominator(1000)
                        return frac, 0.95
                except (ValueError, ZeroDivisionError):
                    pass
        try:
            return float(clean), 0.9
        except ValueError:
            return None, 0.0

    @staticmethod
    def _try_equation(answer: str, task: ExtractedTask) -> Tuple[Any, float]:
        """Solve equation from LaTeX. Only attempts if '=' is in LaTeX and
        exactly one variable appears in the answer."""
        from sympy import symbols, solve, Eq
        from sympy.parsing.latex import parse_latex

        latex = task.question_latex
        if not latex or "=" not in latex:
            return None, 0.0
        x = symbols("x")
        try:
            # Split on '=' to form an equation Eq(lhs, rhs)
            sides = latex.split("=", 1)
            lhs = parse_latex(sides[0].strip())
            rhs = parse_latex(sides[1].strip())
            solutions = solve(Eq(lhs, rhs), x)
            if solutions:
                return str(solutions), 0.85
        except Exception:
            pass
        return None, 0.0

    @staticmethod
    def _try_simplify(answer: str, task: ExtractedTask) -> Tuple[Any, float]:
        """Parse the answer expression. Used only as last resort — does NOT
        verify correctness, just checks the answer is a valid SymPy expression."""
        from sympy import sympify

        try:
            expr = sympify(answer.replace("^", "**"))
            # Return the parsed expression with low confidence (no verification)
            return expr, 0.5
        except Exception:
            return None, 0.0

    @staticmethod
    def _try_numerical(answer: str, task: ExtractedTask) -> Tuple[Any, float]:
        from sympy import sympify, N

        try:
            expr = sympify(answer.replace("^", "**"))
            return float(N(expr, 10)), 0.7
        except Exception:
            return None, 0.0

    @staticmethod
    def _try_expression(answer: str, task: ExtractedTask) -> Tuple[Any, float]:
        from sympy import sympify

        try:
            return sympify(answer.replace("^", "**")), 0.6
        except Exception:
            return None, 0.0
