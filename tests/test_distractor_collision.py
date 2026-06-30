"""Regression matrix for distractor collision false positives."""
import pytest

from src.pipeline.answer_verify import (
    _extract_int_list,
    _int_lists_equivalent,
    answers_equivalent,
)
from src.pipeline.distractor_collision import values_collide_for_distractor
from src.pipeline.distractor_gate import validate_distractor


# ── Must NOT collide (valid distractors) ─────────────────────────────────────

@pytest.mark.parametrize(
    "val,correct,answer_type",
    [
        ("-1/3", "1/3", "expression"),
        ("-2/5", "2/5", "fraction"),
        ("3", "1/3", "expression"),
        ("1 / (a - b)", "1/(a+b)", "set"),
        ("1/(a-b)", "1/(a+b)", "expression"),
        ("x = -2", "x = 2", "equation_solution"),
        ("21 < 2", "21 > 2", "inequality"),
        ("-5(2q - p)", "-5", "expression"),
    ],
)
def test_valid_distractors_do_not_collide(val, correct, answer_type):
    assert not values_collide_for_distractor(val, correct, answer_type), (
        f"{val!r} should not collide with {correct!r} ({answer_type})"
    )


@pytest.mark.parametrize(
    "val,correct,answer_type",
    [
        ("1/3", "1/3", "expression"),
        ("4", "4", "exact_number"),
        ("0,625", "5/8", "fraction"),
        ("x <= 3,5", "x <= 7/2", "inequality"),
        ("1, 2, 3", "3; 2; 1", "set"),
    ],
)
def test_true_equivalents_do_collide(val, correct, answer_type):
    assert values_collide_for_distractor(val, correct, answer_type)


# ── Int-list / fraction parsing ───────────────────────────────────────────────

def test_fraction_not_parsed_as_int_list():
    assert _extract_int_list("1/3") is None
    assert _extract_int_list("3/1") is None
    assert not _int_lists_equivalent("1/3", "3/1")
    assert _extract_int_list("1, 2, 3") == [1, 2, 3]


# ── Substring traps in answers_equivalent ───────────────────────────────────

@pytest.mark.parametrize(
    "val,correct",
    [
        ("-1/3", "1/3"),
        ("3", "1/3"),
        ("12", "2"),
        ("2", "12"),
    ],
)
def test_no_substring_equivalence_exact_number(val, correct):
    assert not answers_equivalent(val, correct, "exact_number")


# ── Gate integration (G8-style tasks) ─────────────────────────────────────────

def test_g8_fraction_sign_distractor_accepted():
    check = validate_distractor(
        question="Представьте частное в виде дроби: -6ax : (-18ax)",
        value="-1/3",
        correct_answer="1/3",
        answer_type="expression",
        error_logic="перепутал знак при сокращении дроби, получил отрицательный результат",
    )
    assert check.ok, check.reason


def test_g8_algebraic_fraction_distractor_accepted():
    check = validate_distractor(
        question="Сократите дробь: (a^2-ab+b^2)/(a^3+b^3)",
        value="1 / (a - b)",
        correct_answer="1/(a+b)",
        answer_type="set",
        error_logic="перепутал знак при разложении суммы кубов на множители",
    )
    assert check.ok, check.reason
