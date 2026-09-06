"""Unit tests for the read-only LaTeX display validator."""
from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_latex_display.py"
_SPEC = importlib.util.spec_from_file_location("validate_latex_display", _SCRIPT)
assert _SPEC and _SPEC.loader
validator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validator)


def _row(**overrides):
    base = {
        "question_text": "Найдите x",
        "question_latex": "Найдите $x$",
        "correct_answer": "2",
        "correct_answer_latex": "$2$",
        "answer_options": [],
        "answer_options_latex": [],
        "distractor_meta": [{
            "value": "1", "value_latex": "$1$",
            "explanation": "Не умножили на два", "explanation_latex": "Не умножили на $2$",
        }],
    }
    base.update(overrides)
    return base


def test_complete_task_is_verified():
    assert validator.validate_task(_row()) == []
    assert validator.expected_status([]) == "verified"


def test_validator_reports_all_missing_display_layers_without_touching_raw_fields():
    row = _row(
        question_latex=None,
        correct_answer_latex=None,
        distractor_meta=[{"text": "1/2", "error_logic": "Перепутан коэффициент"}],
    )

    issues = validator.validate_task(row)

    assert issues == [
        "missing.question_latex",
        "missing.correct_answer_latex",
        "missing.distractor[0].value_latex",
        "missing.distractor[0].description_latex",
    ]
    assert row["distractor_meta"][0] == {"text": "1/2", "error_logic": "Перепутан коэффициент"}
    assert validator.expected_status(issues) == "partial"


def test_validator_requires_direct_display_for_each_plain_answer_option():
    assert validator.validate_task(_row(answer_options=["1", {"value": "1", "value_latex": "$1$"}])) == [
        "missing.answer_options[0].latex",
    ]


def test_validator_prefers_error_logic_over_legacy_explanation_mirror():
    assert validator.validate_task(_row(distractor_meta=[{
        "value": "1", "value_latex": "$1$",
        "explanation": "Разбор", "error_logic": "Неверный шаг",
        "explanation_latex": "Разбор",
    }])) == ["missing.distractor[0].description_latex"]


def test_validator_flags_a_standalone_answer_option_without_display_field():
    assert validator.validate_task(_row(answer_options=["неожиданный вариант"])) == [
        "missing.answer_options[0].latex",
    ]


def test_validator_accepts_parallel_answer_options_latex():
    assert validator.validate_task(_row(
        answer_options=[{"text": "неожиданный вариант"}],
        answer_options_latex=["неожиданный вариант"],
    )) == []


def test_validator_rejects_unwrapped_mathematical_values_but_allows_prose():
    assert validator.validate_task(_row(
        correct_answer_latex="2",
        distractor_meta=[{
            "value": "Функция возрастает", "value_latex": "Функция возрастает",
            "explanation": "Текст", "explanation_latex": "Текст",
        }],
    )) == ["contract.correct_answer_latex"]


def test_semantic_audit_rejects_display_question_that_drops_instruction_text():
    row = _row(
        question_text=r"Упростите выражение $\frac{x}{2}$ и найдите его значение при $x=4$.",
        question_latex=r"$\dfrac{x}{2}, \quad x=4$",
        distractor_meta=[],
    )

    assert validator.validate_task(row, check_semantics=True) == ["semantic.question_latex"]


def test_semantic_audit_accepts_safe_fraction_normalization():
    row = _row(
        question_text=r"Найдите $\frac{x^2+1}{2}$.",
        question_latex=r"Найдите $\dfrac{x^{2}+1}{2}$.",
        distractor_meta=[],
    )

    assert validator.validate_task(row, check_semantics=True) == []


def test_audit_rejects_parseable_but_non_professional_latex():
    row = _row(
        question_text=r"Найдите $x^2$.",
        question_latex=r"Найдите $x^2$.",
    )

    assert validator.validate_task(row) == ["professional.question_latex"]
