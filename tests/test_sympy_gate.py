"""Tests for answer_sympy_gate — namespace, canonical resolve, Abs equations."""
from src.pipeline.answer_sympy_gate import (
    SympyGateResult,
    evaluate_sympy_string,
    format_school_notation,
    resolve_canonical_answer,
    solve_equation_from_question,
    sympy_gate,
)


def test_abs_equation_solve_from_question():
    q = "Решите уравнение:\n|7+3*x| = 0"
    expected = solve_equation_from_question(q, "equation_solution")
    assert expected is not None
    # -7/3 in some form
    assert "-7" in expected or "-2" in expected


def test_sympy_gate_abs_equation_string():
    sympy_str = "Eq(Abs(7+3*x), 0)"
    gate = sympy_gate(
        sympy_str,
        "x = -7/3",
        "equation_solution",
        question="|7+3x| = 0",
        stored_answer="x = -2(1/3)",
    )
    assert gate.ok, gate.reason
    assert gate.computed_local is not None


def test_resolve_canonical_local_sympy():
    gate = SympyGateResult(ok=True, computed_local="x = -7/3", reason="sympy_match")
    canonical, source = resolve_canonical_answer(
        gate, "x = -2 1/3", question="|7+3x|=0", answer_type="equation_solution",
    )
    assert source == "local_sympy"
    assert "-7" in canonical


def test_resolve_canonical_llm_fallback():
    gate = SympyGateResult(ok=True, computed_local="x = -2 1/3", reason="textbook_agrees_with_llm")
    canonical, source = resolve_canonical_answer(
        gate, "x = -2 1/3", answer_type="equation_solution",
    )
    assert source == "llm_fallback"
    assert canonical == "x = -2 1/3"


def test_evaluate_sympy_string_eq():
    result = evaluate_sympy_string("Eq(2*x - 4, 10)", "equation_solution")
    assert result is not None
    assert "7" in result


def test_format_school_notation_fraction():
    out = format_school_notation("-7/3", "equation_solution")
    assert out == "-7/3" or "-7" in out
