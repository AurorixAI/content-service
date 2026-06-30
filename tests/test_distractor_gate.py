"""Tests for distractor_gate L1–L4."""
from src.pipeline.distractor_gate import (
    stored_distractors_valid,
    validate_distractor,
    validate_distractor_set,
)


def test_text_peer_distinct_prose_after_verdict_prefix():
    """G8 text: «нет, так как A» and «нет, так как B» are different distractors."""
    a = "нет, так как при записи x = 5,8 ± 0,2 точное значение может быть только целым числом"
    b = "нет, так как при округлении 5,9 до целых получается 6, а 5,8 тоже округляется до 6"
    accepted, rejected = validate_distractor_set(
        [
            {"value": a, "error_logic": "ошибочно считает, что точное значение обязано быть целым"},
            {"value": b, "error_logic": "путает округление с точным значением в интервале погрешности"},
            {"value": "нет, так как погрешность ±0,2 не позволяет отличить 5,8 от 6,2", "error_logic": "ошибочно отвергает утверждение из-за неверной оценки интервала"},
        ],
        question="Можно ли считать x = 5,8 точным значением, если x = 5,8 ± 0,2?",
        correct_answer="да",
        answer_type="text",
        max_count=3,
    )
    assert len(accepted) == 3
    assert not rejected


def test_text_peer_numeric_still_collides():
    accepted, rejected = validate_distractor_set(
        [
            {"value": "220.5", "error_logic": "ошибся при переводе единиц измерения в ответе"},
            {"value": "220,5", "error_logic": "записал десятичную точку вместо запятой, но то же число"},
        ],
        question="Найдите значение.",
        correct_answer="210",
        answer_type="text",
        max_count=2,
    )
    assert len(accepted) == 1
    assert rejected[0]["gate_reason"] == "collision_peer"


def test_reject_collision_with_correct():
    check = validate_distractor(
        question="2+2",
        value="4",
        correct_answer="4",
        answer_type="exact_number",
        error_logic="перепутал знак при сложении",
    )
    assert not check.ok
    assert check.reason == "collision_correct"


def test_reject_implausible_no_error_logic():
    check = validate_distractor(
        question="x",
        value="5",
        correct_answer="2",
        answer_type="exact_number",
        error_logic="short",
    )
    assert not check.ok
    assert check.reason == "implausible"


def test_reject_garbage_parse():
    check = validate_distractor(
        question="q",
        value="не знаю",
        correct_answer="4",
        answer_type="exact_number",
        error_logic="ученик не знает ответ на задачу",
    )
    assert not check.ok
    assert check.reason == "parse_failed"


def test_accept_reasonable_numeric_distractor():
    check = validate_distractor(
        question="Сколько будет 2+2?",
        value="5",
        correct_answer="4",
        answer_type="exact_number",
        error_logic="ошибся при сложении единицы",
    )
    assert check.ok


def test_reject_equation_that_solves():
    check = validate_distractor(
        question="Решите: |7+3x| = 0",
        value="x = -7/3",
        correct_answer="x = -7/3",
        answer_type="equation_solution",
        error_logic="скопировал правильный ответ по ошибке",
    )
    assert not check.ok


def test_stored_distractors_valid_rejects_subset_of_answer():
    dmeta = [
        {"value": "x = 2,5", "error_logic": "взял только один корень из двух"},
        {"value": "x = -2,5", "error_logic": "взял второй корень отдельно"},
        {"value": "Решений нет", "error_logic": "решил что уравнение не имеет корней"},
    ]
    ok = stored_distractors_valid(
        dmeta,
        question="Решите уравнение",
        correct_answer="x = 2,5; x = -2,5",
        answer_type="equation_solution",
    )
    assert not ok


def test_accept_two_distractors_minimum():
    items = [
        {"value": "5", "error_logic": "ошибся при сложении единицы"},
        {"value": "3", "error_logic": "вычел единицу вместо прибавления"},
    ]
    accepted, _ = validate_distractor_set(
        items,
        question="2+2=?",
        correct_answer="4",
        answer_type="exact_number",
        max_count=3,
        skip_l3=True,
    )
    assert len(accepted) == 2


def test_validate_set_filters_collisions():
    items = [
        {"value": "4", "error_logic": "ошибка при вычислении суммы"},
        {"value": "5", "error_logic": "добавил лишнюю единицу к ответу"},
        {"value": "3", "error_logic": "вычел единицу вместо прибавления"},
    ]
    accepted, rejected = validate_distractor_set(
        items,
        question="2+2=?",
        correct_answer="4",
        answer_type="exact_number",
        max_count=3,
        skip_l3=True,
    )
    assert len(accepted) == 2
    assert any(r.get("gate_reason") == "collision_correct" for r in rejected)


def test_reject_text_mixed_fraction_equivalent_to_improper():
    check = validate_distractor(
        question="Вычислите: 2 1/4 * (16/17) * (17/16)",
        value="2 1/4",
        correct_answer="9/4",
        answer_type="text",
        error_logic="перепутал вид ответа, но значение совпадает с верным",
    )
    assert not check.ok
    assert check.reason == "collision_correct"


def test_reject_comparison_answer_with_wrong_reasoning_suffix():
    q = "Сравните дроби 19/60 и 4/15"
    correct = "19/60 > 4/15"
    check = validate_distractor(
        question=q,
        value="19/60 > 4/15, так как 19 > 4 и 60 > 15",
        correct_answer=correct,
        answer_type="expression",
        error_logic="сравнил числители и знаменатели по отдельности, случайно угадал знак",
    )
    assert not check.ok
    assert check.reason in ("collision_correct", "solves_question")


def test_reject_empty_error_logic_on_text():
    check = validate_distractor(
        question="2+2",
        value="5",
        correct_answer="4",
        answer_type="text",
        error_logic="",
    )
    assert not check.ok
    assert check.reason == "implausible"


def test_accept_wrong_sign_fraction_comparison():
    check = validate_distractor(
        question="Сравните дроби 19/60 и 4/15",
        value="19/60 < 4/15",
        correct_answer="19/60 > 4/15",
        answer_type="expression",
        error_logic="сравнил только знаменатели и перепутал знак неравенства",
    )
    assert check.ok


def test_stored_invalid_when_one_of_three_embeds_correct():
    dmeta = [
        {"value": "19/60 < 4/15", "error_logic": "ошибка при сравнении знаменателей дробей"},
        {"value": "19/60 > 4/15, потому что 19 - 60 > 4 - 15", "error_logic": "вычитал числитель из знаменателя вместо НОК"},
        {"value": "19/60 > 4/15, так как 19 > 4 и 60 > 15", "error_logic": "сравнил части дроби отдельно и случайно угадал знак"},
    ]
    ok = stored_distractors_valid(
        dmeta,
        question="Сравните дроби 19/60 и 4/15",
        correct_answer="19/60 > 4/15",
        answer_type="expression",
        min_count=2,
    )
    assert not ok


def test_inequality_distractors_not_false_peer_collision():
    items = [
        {"value": "3 > 16", "error_logic": "неверно сложил левые части неравенств"},
        {"value": "21 < 3", "error_logic": "перепутал знак итогового неравенства"},
        {"value": "20 < 2", "error_logic": "ошибка при сложении правых частей"},
    ]
    accepted, _ = validate_distractor_set(
        items,
        question="Сложите почленно: 12>-5 и 9>7",
        correct_answer="21 > 2",
        answer_type="inequality",
        max_count=3,
        skip_l3=True,
    )
    assert len(accepted) >= 2


def test_set_algebraic_fractions_not_int_list_collision():
    """1/(a-b) vs 1/(a+b) must not collide when answer_type is set (G8_TB_2_33.1)."""
    from src.pipeline.answer_verify import _int_lists_equivalent, answers_equivalent

    assert not _int_lists_equivalent("1 / (a - b)", "1/(a+b)")
    assert not answers_equivalent("1 / (a - b)", "1/(a+b)", "set")

    check = validate_distractor(
        question="Сократите дробь: (a^2-ab+b^2)/(a^3+b^3)",
        value="1 / (a - b)",
        correct_answer="1/(a+b)",
        answer_type="set",
        error_logic="ученик перепутал знак при разложении суммы кубов на множители",
    )
    assert check.ok, check.reason


def test_int_list_still_works_for_real_sets():
    from src.pipeline.answer_verify import _int_lists_equivalent, _extract_int_list

    assert _extract_int_list("1, 2, 3") == [1, 2, 3]
    assert _extract_int_list("-3, 0, 5") == [-3, 0, 5]
    assert _int_lists_equivalent("2, 1, 3", "1; 2; 3")
    assert _extract_int_list("1/(a+b)") is None


def test_fraction_sign_distractors_not_substring_collision():
    """-1/3 and 3 are valid distractors when answer is 1/3 (G8_TB_2_27.4.2)."""
    from src.pipeline.answer_verify import answers_equivalent

    assert not answers_equivalent("-1/3", "1/3", "exact_number")
    assert not answers_equivalent("3", "1/3", "exact_number")

    check_neg = validate_distractor(
        question="Представьте частное в виде дроби: -6ax : (-18ax)",
        value="-1/3",
        correct_answer="1/3",
        answer_type="expression",
        error_logic="перепутал знак при сокращении дроби, получил отрицательный результат",
    )
    assert check_neg.ok, check_neg.reason

    check_three = validate_distractor(
        question="Представьте частное в виде дроби: -6ax : (-18ax)",
        value="3",
        correct_answer="1/3",
        answer_type="expression",
        error_logic="перепутал деление с сокращением и получил целое число 3",
    )
    assert check_three.ok, check_three.reason
