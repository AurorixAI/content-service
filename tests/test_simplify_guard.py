"""Заслон на выражениях, которые вешают SymPy.

Найдено живым замером по выгрузке прода 2026-09-02. Задача `G7_ALG_18_13.4`
несёт ответ `a^{36} - 3a^{24b}^{13} + …` — испорченный распознаванием
`a^{24}b^{13}`, где показателем степени стала переменная. Разбор превращает
`(24*b)**13` в показатель `876488338465357824*b**13`, и численная подстановка
заставляет Python считать целое число с квинтиллионом цифр.

Гейт дистракторов на этой задаче не возвращался больше двух минут. Прервать
его снаружи нельзя: `signal.alarm` не срабатывает, пока SymPy внутри C-кода —
проверено, будильник на 5 секунд не сработал за 120.
"""
import time

from src.pipeline.answer_sympy import (
    _MAX_EXPONENT,
    _too_hard_for_simplify,
    monte_carlo_equivalent,
    parse_expr,
    sympy_equivalent,
)
from src.pipeline.distractor_gate import validate_distractor_set

BROKEN_OCR_ANSWER = "$a^{36} - 3a^{24b}^{13} + 3a^{12b}^{26} - b^{39}$"


class TestTooHardForSimplify:
    def test_symbolic_exponent_is_refused(self):
        expr = parse_expr("a**(24*b)")
        assert expr is not None
        assert _too_hard_for_simplify(expr) is True

    def test_huge_numeric_exponent_is_refused(self):
        expr = parse_expr(f"x**{_MAX_EXPONENT + 10}")
        assert expr is not None
        assert _too_hard_for_simplify(expr) is True

    def test_ordinary_school_expression_is_allowed(self):
        for src in ("2*x + 3", "x**2 - 4", "(a + b)**3", "3/4", "sqrt(2)*x"):
            expr = parse_expr(src)
            assert expr is not None, src
            assert _too_hard_for_simplify(expr) is False, src

    def test_exponent_at_the_limit_is_allowed(self):
        expr = parse_expr(f"x**{_MAX_EXPONENT}")
        assert _too_hard_for_simplify(expr) is False


class TestGuardedComparison:
    def test_refusal_is_unknown_not_difference(self):
        """«Не берусь» обязано отличаться от «выражения разные»."""
        assert monte_carlo_equivalent(BROKEN_OCR_ANSWER, "$a^{36} - b^{39}$") is None

    def test_equivalence_still_works_on_normal_input(self):
        assert sympy_equivalent("(x + 1)**2", "x**2 + 2*x + 1") is True

    def test_difference_still_detected_on_normal_input(self):
        assert sympy_equivalent("x + 1", "x + 2") is False


class TestNoHang:
    def test_broken_ocr_task_completes_quickly(self):
        """До заслона этот вызов не возвращался больше 120 секунд."""
        distractors = [
            {"value": "$a^{36} - b^{39}$", "error_logic": "потерял средние члены куба разности"},
            {"value": "$a^{15} - 3a^{24}b^{13} + 3a^{12}b^{26} - b^{16}$",
             "error_logic": "перемножил показатели вместо умножения на 3"},
            {"value": "$a^{36} - 3a^{24}b^{13} - 3a^{12}b^{26} - b^{39}$",
             "error_logic": "перепутал знаки у средних членов"},
        ]
        started = time.perf_counter()
        validate_distractor_set(
            distractors,
            question="Представьте в виде многочлена: $(a^{12}-b^{13})^3$",
            correct_answer=BROKEN_OCR_ANSWER,
            answer_type="expression",
            max_count=3,
            skip_l3=True,
        )
        assert time.perf_counter() - started < 10.0
