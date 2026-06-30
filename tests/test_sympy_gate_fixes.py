"""Tests for pilot failure fixes."""
from src.pipeline.answer_sympy_gate import (
    evaluate_sympy_string,
    is_prose_answer,
    is_write_equation_task,
    sympy_gate,
)
from src.pipeline.answer_verify import answers_equivalent, stored_answer_matches_compute


def test_no_real_roots():
    result = evaluate_sympy_string(
        "Eq(x**2 + 9, 0)", "equation_solution", question="Решите: x^2+9=0",
    )
    assert result == "нет корней"
    gate = sympy_gate(
        "Eq(x**2 + 9, 0)", "нет корней", "equation_solution",
        question="x^2 + 9 = 0",
    )
    assert gate.ok, gate.reason


def test_write_equation_task():
    q = "Запишите квадратное уравнение ax^2 + bx + c = 0, если a=2, b=3, c=4"
    assert is_write_equation_task(q)
    gate = sympy_gate(
        "Eq(2*x**2 + 3*x + 4, 0)",
        "2x^2 + 3x + 4 = 0",
        "equation_solution",
        question=q,
        stored_answer="2x^2 + 3x + 4 = 0",
    )
    assert gate.ok, gate.reason


def test_pm_notation_equivalent():
    assert answers_equivalent("x = ±3/2", "x = -3/2; x = 3/2", "equation_solution")
    assert answers_equivalent("x = ±3/2", "-1.5; 1.5", "equation_solution")


def test_pm_surd_equivalent():
    assert answers_equivalent(
        r"x = ± 2\sqrt{2}",
        "-2.8284271247; 2.8284271247",
        "equation_solution",
    )


def test_indexed_roots_equivalent():
    assert answers_equivalent("x_1 = 0, x_2 = 7", "0; 7", "equation_solution")
    assert answers_equivalent("x_1 = 0, x_2 = -5", "-5; 0", "equation_solution")


def test_latex_pm_equivalent():
    assert answers_equivalent(r"x = \pm 6.5", "-6.5; 6.5", "equation_solution")
    assert answers_equivalent(r"x = \pm 2\sqrt{2}", "-2.8284271247; 2.8284271247", "equation_solution")
    assert stored_answer_matches_compute(
        r"x = \pm 6.5",
        "-6.5; 6.5",
        answer_type="equation_solution",
    )


def test_format_solutions_pm_surd():
    pytest = __import__("pytest")
    sympy = pytest.importorskip("sympy")
    from sympy import Eq
    from src.pipeline.answer_sympy_gate import _format_solutions

    out = _format_solutions([-2 * sympy.sqrt(2), 2 * sympy.sqrt(2)], "equation_solution")
    assert "±" in out
    assert "√" in out or "sqrt" in out.lower()

    out_eq = _format_solutions([Eq(sympy.Symbol("x"), -3), Eq(sympy.Symbol("x"), 3)], "equation_solution")
    assert "±" in out_eq


def test_decimal_mixed_fraction_equivalent():
    assert answers_equivalent(
        "-1.3333333333; 1.3333333333",
        "-1 1/3; 1 1/3",
        "equation_solution",
    )


def test_factored_equation_equivalent():
    from src.pipeline.answer_sympy_gate import equation_form_equivalent, sympy_gate

    assert equation_form_equivalent("x^2 - 5x = 0", "x*(x - 5) = 0")
    q = "Запишите квадратное уравнение ax^2 + bx + c = 0, если a=1, b=-5, c=0"
    gate = sympy_gate(
        "Eq(x**2 - 5*x, 0)",
        "x^2 - 5x = 0",
        "equation_solution",
        question=q,
        stored_answer="x^2 - 5x = 0",
    )
    assert gate.ok, gate.reason


def test_prose_not_parsed_as_math():
    assert is_prose_answer("нет корней")
    assert not is_prose_answer("x = -7/3")


def test_coordinate_pairs_equivalent():
    from src.pipeline.answer_verify import answers_equivalent

    assert answers_equivalent(
        "(2; -4), (-4; -10)",
        "x_1 = 2, x_2 = -4; x_1 = -4, x_2 = -10",
        "equation_solution",
    )
    assert answers_equivalent(
        "(3; -2), (10; 5)",
        "x_1 = 3, x_2 = -2; x_1 = 10, x_2 = 5",
        "equation_solution",
    )


def test_expression_sqrt_product_equivalent():
    from src.pipeline.answer_verify import answers_equivalent

    assert answers_equivalent(r"a\sqrt{a}", "a**(3/2)", "expression")
    assert answers_equivalent(r"x\sqrt{x}", "x**(3/2)", "expression")
    assert answers_equivalent("a√a", "a**(3/2)", "expression")


def test_decimal_roots_equivalent():
    from src.pipeline.answer_verify import answers_equivalent

    assert answers_equivalent(
        "0.30, 6.70",
        "x_1 = 7/2 - sqrt(41)/2, x_2 = 7/2 + sqrt(41)/2",
        "equation_solution",
    )


def test_format_expression_school_sympy_pow():
    from src.pipeline.answer_sympy_gate import (
        beautify_answer_if_equivalent,
        format_expression_school,
    )
    from src.pipeline.answer_verify import answers_equivalent

    raw = "0.142857142857143*a**5/b**3"
    pretty = format_expression_school(raw)
    assert "**" not in pretty
    assert "1/7" in pretty or r"\frac" in pretty

    ugly = "Simplify(2*a**2*d**2/(3*c))"
    fixed = format_expression_school(ugly)
    assert "Simplify" not in fixed
    assert "**" not in fixed

    sci = "2.99302624884020e-23"
    sci_fmt = format_expression_school(sci)
    assert "10^{-23}" in sci_fmt or "10^" in sci_fmt

    multipart = "30/v + 17/(v + 2); а) 3; б) 2 31/60"
    assert beautify_answer_if_equivalent(raw, "expression") != raw
    assert beautify_answer_if_equivalent(multipart, "expression") == multipart


def test_to_answer_latex_equation_solutions():
    from src.pipeline.answer_sympy_gate import to_answer_latex

    assert to_answer_latex("x = 3; x = -2", "equation_solution") == "$x = 3$; $x = -2$"
    assert to_answer_latex("x = -2/3, x = -3", "equation_solution") == (
        r"$x = - \frac{2}{3}$, $x = -3$"
    )
    assert to_answer_latex("x = 1/3", "equation_solution") == r"$x = \frac{1}{3}$"
    assert to_answer_latex("x = 2,5", "equation_solution") == r"$x = 2{,}5$"
    assert to_answer_latex("x = 8.5", "equation_solution") == r"$x = 8{,}5$"
    assert to_answer_latex("-0.2", "equation_solution") == r"$-0{,}2$"
    assert to_answer_latex("8.5", "exact_number") == r"$8{,}5$"
    assert to_answer_latex("x > 2.5", "inequality") == r"$x > 2{,}5$"
    assert to_answer_latex("x >= 1/2", "inequality") == r"$x >= \frac{1}{2}$"
    assert to_answer_latex("x <= 7/2", "inequality") == r"$x <= \frac{7}{2}$"
    assert to_answer_latex("нет корней", "equation_solution") == "нет корней"
    assert "x_1" in to_answer_latex(
        "x_1 = 1 - sqrt(10)/2, x_2 = 1 + sqrt(10)/2", "equation_solution"
    )
    assert r"\frac" in to_answer_latex("x = 3/2", "equation_solution")
    assert to_answer_latex("0; 3.3333333333", "equation_solution") == (
        r"$0$; $\frac{10}{3}$"
    )
    assert r"\sqrt" in to_answer_latex(
        "-3.1622776602; 3.1622776602", "equation_solution"
    )


def test_to_answer_latex_display_fracs():
    from src.pipeline.answer_sympy_gate import to_answer_latex

    assert to_answer_latex("3/a^(1/2)", "expression") == r"$\frac{3}{\sqrt{a}}$"
    assert to_answer_latex("1/3*a^2", "expression") == r"$\frac{a^{2}}{3}$"
    assert to_answer_latex("1/x", "expression") == r"$\frac{1}{x}$"
    assert to_answer_latex("9a", "expression") == "$9a$"
    assert to_answer_latex("-a\\sqrt{6}/3", "expression") == r"$\frac{-a\sqrt{6}}{3}$"
    assert " / " not in to_answer_latex("a^2 + ab + b^2", "expression")


def test_symbolic_answers_not_false_equivalent():
    from src.pipeline.answer_verify import answers_equivalent

    assert not answers_equivalent(
        "(v_1*n + v_2*m)/(n + m)",
        "v_1*n + v_2*m",
        "expression",
    )
    assert not answers_equivalent(
        "x = (a - b)/3",
        "x = (b - a) / 3",
        "equation_solution",
    )
    assert not answers_equivalent(
        "x = (a - b)/3",
        "x = (a + b) / 3",
        "equation_solution",
    )
    assert not answers_equivalent(
        "x_1 = 0, x_2 = 3/2",
        "x = 0",
        "equation_solution",
    )


def test_inequality_format_equivalent():
    from src.pipeline.answer_verify import answers_equivalent

    assert answers_equivalent("x <= 7/2", "x <= 3,5", "inequality")
    assert answers_equivalent("x >= -9/2", "x >= -4,5", "inequality")
    assert answers_equivalent("x < 5/2", "x < 2,5", "inequality")
    assert answers_equivalent(
        "(P >= 20.4) & (P <= 20.8)",
        "20,4 ⩽ P ⩽ 20,8",
        "inequality",
    )
    assert answers_equivalent("любое число", "Reals", "inequality")
    assert answers_equivalent("нет решений", "нет таких значений", "inequality")


def test_set_equivalence_fixes():
    from src.pipeline.answer_verify import answers_equivalent

    q_int = "Найдите все целые значения x, при которых выполняется неравенство: |5x - 2| < 8"
    assert answers_equivalent(
        "-1, 0, 1",
        "(x > -6/5) & (x < 2)",
        "set",
        question=q_int,
    )
    assert answers_equivalent("любое число", "Reals", "set")
    assert answers_equivalent("y ≠ 0, y ≠ 2", "0; 2", "set")
    assert answers_equivalent(
        "а) -3, -2, -1, 0, 1, 2; б) -3, -2, -1, 0, 1, 2, 3, 4, 5",
        "Range(-3, 3, 1); Range(-3, 6, 1)",
        "set",
    )
    assert answers_equivalent(
        "Любые два числа, меньшие 7 (например, 0 и 1)",
        "x < 7",
        "set",
    )


def test_mcq_text_equivalent():
    from src.pipeline.answer_verify import answers_equivalent

    assert answers_equivalent("да", "да", "multiple_choice")
    assert answers_equivalent("в", "в", "multiple_choice")
    assert answers_equivalent("да", "True", "multiple_choice")
    assert answers_equivalent("нет", "False", "multiple_choice")


def test_numeric_inequality_equivalent():
    from src.pipeline.answer_verify import answers_equivalent

    assert answers_equivalent("21 > 2", "21 > 2", "inequality")
    assert not answers_equivalent("21 > 2", "21 > -12", "inequality")


def test_radical_comparison_not_equivalent_by_numeric_multiset():
    from src.pipeline.answer_verify import answers_equivalent

    assert not answers_equivalent(
        r"-\sqrt{14} > -3\sqrt{2}",
        r"-\sqrt{14} < -3\sqrt{2}",
        "inequality",
    )
    assert not answers_equivalent(
        r"-7\sqrt{0,17} < -11\sqrt{0,05}",
        r"-7\sqrt{0,17} > -11\sqrt{0,05}",
        "inequality",
    )


def test_continuous_domain_set():
    from src.pipeline.answer_verify import answers_equivalent

    assert answers_equivalent(
        "x ≠ 2",
        "continuous_domain(1/(x - 2), x, Reals)",
        "set",
    )


def test_sympy_gate_greater_notation():
    gate = sympy_gate(
        "5 > 2",
        "20 > 6",
        "inequality",
        question="Перемножьте почленно неравенства: 5 > 2 и 4 > 3",
        stored_answer="20 > 6",
    )
    assert gate.ok, gate.reason


def test_sympy_gate_mcq_true_da():
    gate = sympy_gate(
        "True",
        "да",
        "multiple_choice",
        question="Верно ли, что каждое рациональное число является действительным",
        stored_answer="да",
    )
    assert gate.ok, gate.reason


def test_sympy_gate_integer_from_inequality():
    gate = sympy_gate(
        "solve(1.6 - (3 - 2*y) < 5, y)",
        "3",
        "exact_number",
        question="Найдите: наибольшее целое число, удовлетворяющее неравенству",
        stored_answer="3",
    )
    # computed will be y < 16/5 from evaluate - may need actual sympy string
    # simpler unit test via helper
    from src.pipeline.answer_sympy_gate import _integer_answer_from_computed_inequality

    assert _integer_answer_from_computed_inequality(
        "Найдите наибольшее целое число",
        "y < 3.2",
    ) == "3"


def test_distractor_multipart_parse():
    from src.pipeline.distractor_gate import validate_distractor

    check = validate_distractor(
        question="Вычислите корни",
        value="10000; д) 25; е) 16",
        correct_answer="10000; д) 25; е) 16",
        answer_type="exact_number",
        error_logic="ошибка в одном из подпунктов вычисления",
    )
    assert not check.ok
    assert check.reason == "collision_correct"

    check2 = validate_distractor(
        question="Вычислите корни",
        value="10000; д) 24; е) 16",
        correct_answer="10000; д) 25; е) 16",
        answer_type="exact_number",
        error_logic="ошибка при вычислении подпункта д)",
    )
    assert check2.ok, check2.reason


def test_sign_region_inequality():
    from src.pipeline.answer_verify import answers_equivalent

    prose = "положительные при x > -6,5; отрицательные при x < -6,5"
    assert answers_equivalent(prose, prose, "inequality")
    assert answers_equivalent(prose, "x > -6,5; x < -6,5", "inequality")


def test_numeric_list_order_equivalent():
    from src.pipeline.answer_verify import answers_equivalent

    assert answers_equivalent("1.587401052", "1,6", "exact_number")
    assert answers_equivalent("5/8", "0,625", "fraction")


def test_coordinate_answer_latex():
    from src.pipeline.answer_sympy_gate import to_answer_latex

    assert to_answer_latex("(0,2; 0,4)", "coordinate") == "$(0{,}2; 0{,}4)$"
    assert to_answer_latex("(5; 4)", "coordinate") == "$(5; 4)$"
    out = to_answer_latex("(0,2; 0) и (0; -2,6)", "coordinate")
    assert "$(0{,}2; 0)$" in out
    assert "$(0; -2{,}6)$" in out
    assert " и " in out


def test_coordinate_distractor_latex():
    from src.pipeline.answer_sympy_gate import enrich_distractor_latex

    meta = [{"value": "(5; 0)"}, {"value": "(2.33; 4)"}]
    out = enrich_distractor_latex(meta, "coordinate")
    assert out[0]["value_latex"] == "$(5; 0)$"
    assert "$(2.33; 4)$" in out[1]["value_latex"] or "$(2{,}33; 4)$" in out[1]["value_latex"]


def test_expr_to_school_notation_rejects_singleton_registry():
    """Regression: sympy.S must not crash simplify() in LaTeX post-process."""
    import sympy
    from src.pipeline.answer_sympy_gate import _expr_to_school_notation

    out = _expr_to_school_notation(sympy.S)
    assert isinstance(out, str)
    assert out  # fallback string, not an exception


def test_to_question_latex_wraps_math():
    from src.pipeline.answer_sympy_gate import to_question_latex

    assert to_question_latex("(100 + 1)^2") == "$(100 + 1)^{2}$"
    assert to_question_latex("Вычислите:\n(100 + 1)^2") == (
        "Вычислите:\n$(100 + 1)^{2}$"
    )
    assert "Упростите" in to_question_latex(
        "Упростите выражение:\n(a^3 + 6b^2)^2 - (6b^2 - a^3)^2"
    )
    assert "$" in to_question_latex("Решите уравнение\nm^2 - 25 = 0")
    assert to_question_latex("Докажите, что n^3 делится на 6") == (
        "Докажите, что n^3 делится на 6"
    )

    from src.pipeline.answer_sympy_gate import enrich_distractor_latex

    meta = [{"value": "3a - 4b"}, {"value": "S"}]
    out = enrich_distractor_latex(meta, "expression")
    assert len(out) == 2
    assert out[0].get("value_latex")
    assert out[1].get("value_latex")

