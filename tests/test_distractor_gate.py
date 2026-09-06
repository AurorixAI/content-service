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


def test_legacy_exact_number_coordinate_answer_uses_solution_set_gate():
    check = validate_distractor(
        question="Решите систему уравнений и запишите пару (x; y).",
        value="x = 2, y = 1",
        correct_answer="x = 1, y = 1",
        answer_type="exact_number",
        error_logic="Ученик неверно перенёс свободный член при сложении уравнений.",
        skip_l3=True,
    )
    assert check.ok, check.reason


def test_legacy_exact_number_multi_solution_keeps_changed_component_distinct():
    check = validate_distractor(
        question="Решите систему уравнений и укажите все пары решений.",
        value="x = 0, y = 0; x = 1, y = 1",
        correct_answer="x = 0, y = 0; x = 1, y = -1",
        answer_type="exact_number",
        error_logic="Ученик потерял минус при записи второй пары решения системы.",
        skip_l3=True,
    )
    assert check.ok, check.reason


def test_legacy_exact_number_interval_answer_uses_interval_gate():
    check = validate_distractor(
        question="Найдите множество решений системы неравенств.",
        value="(-1; 2)",
        correct_answer="[-1; 2)",
        answer_type="exact_number",
        error_logic="Ученик не включил граничную точку после решения неравенства.",
        skip_l3=True,
    )
    assert check.ok, check.reason


def test_legacy_latex_fraction_interval_uses_interval_gate():
    from src.pipeline.distractor_gate import effective_distractor_answer_type

    question = r"Решите двойное неравенство: -1\leq\frac{3-4x}{2}<5."
    answer = r"$\left(-\frac{7}{4}; \frac{5}{4}\right]$"

    assert effective_distractor_answer_type(
        question, answer, "exact_number",
    ) == "inequality"


def test_legacy_exact_number_coordinate_pair_is_not_parsed_as_interval():
    check = validate_distractor(
        question="Запишите координаты точки B в стандартном виде (x; y).",
        value="(17; -9)",
        correct_answer="(-3; -9)",
        answer_type="exact_number",
        error_logic="Ученик прибавил десять к абсциссе вместо вычитания десяти.",
        skip_l3=True,
    )
    assert check.ok, check.reason


def test_legacy_full_comparison_answer_accepts_only_other_signs():
    good = validate_distractor(
        question="Сравните 2^5 и 5^2. Выберите верный знак неравенства.",
        value="<",
        correct_answer="2^5 > 5^2",
        answer_type="exact_number",
        error_logic="Ученик перепутал результаты вычисления степеней и выбрал обратный знак.",
        skip_l3=True,
    )
    bad = validate_distractor(
        question="Сравните 2^5 и 5^2. Выберите верный знак неравенства.",
        value="2^5 < 5^2",
        correct_answer="2^5 > 5^2",
        answer_type="exact_number",
        error_logic="Ученик перепутал результаты вычисления степеней и выбрал обратный знак.",
        skip_l3=True,
    )
    assert good.ok, good.reason
    assert not bad.ok
    assert bad.reason == "invalid_comparison_choice"


def test_legacy_exact_number_trigonometric_components_keep_wrong_sign_distinct():
    check = validate_distractor(
        question="Дано: ctg α = -7/24. Найдите sin α, cos α и tg α.",
        value="sin α = 24/25, cos α = 7/25, tg α = 24/7",
        correct_answer="sin α = 24/25, cos α = -7/25, tg α = -24/7",
        answer_type="exact_number",
        error_logic="Ученик не учёл вторую четверть и потерял знаки косинуса и тангенса.",
        skip_l3=True,
    )
    assert check.ok, check.reason


def test_legacy_exact_number_wrong_formula_variable_is_not_correct_answer():
    check = validate_distractor(
        question="Выразите m2 из формулы температуры смеси.",
        value="m1 = m2*c2*(T2-T)/(c1*(T-T1))",
        correct_answer="m2*c2*(T-T2)/(c1*(T1-T))",
        answer_type="exact_number",
        error_logic="Ученик выразил другую переменную вместо требуемой m2.",
        skip_l3=True,
    )
    assert check.ok, check.reason


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


def test_exact_number_legacy_comparison_distractor_does_not_crash():
    check = validate_distractor(
        question="Сравните результаты. Запишите знак: A ... K.",
        value="$>$",
        correct_answer="$<$",
        answer_type="exact_number",
        error_logic="Ученик перепутал большее и меньшее значения и выбрал обратный знак.",
        skip_l3=True,
    )
    assert check.ok, check.reason


def test_exact_number_legacy_comparison_set_does_not_crash_on_peer_collision():
    accepted, rejected = validate_distractor_set(
        [
            {"value": "$>$", "error_logic": "Ученик перепутал левую и правую части сравнения."},
            {"value": "$=$", "error_logic": "Ученик решил, что вычисленные значения совпадают."},
        ],
        question="Сравните результаты. Запишите знак: A ... K.",
        correct_answer="$<$",
        answer_type="exact_number",
        max_count=2,
        skip_l3=True,
    )
    assert len(accepted) == 2
    assert not rejected


def test_comparison_sign_task_requires_two_unique_wrong_signs_only():
    from src.pipeline.distractor_gate import stored_distractors_valid
    from src.pipeline.distractors import (
        _minimum_distractor_count,
        _required_distractor_count,
    )

    question = "Сравните результаты. Запишите знак: A ... K."
    assert _minimum_distractor_count("<", "exact_number", question) == 2
    assert _required_distractor_count("<", "exact_number", question) == 2
    assert stored_distractors_valid(
        [
            {"value": ">", "error_logic": "Ученик перепутал направление сравнения чисел."},
            {"value": "=", "error_logic": "Ученик ошибочно решил, что значения равны."},
        ],
        question=question,
        correct_answer="<",
        answer_type="exact_number",
        min_count=2,
    )
    assert not stored_distractors_valid(
        [
            {"value": ">", "error_logic": "Ученик перепутал направление сравнения чисел."},
            {"value": "=", "error_logic": "Ученик ошибочно решил, что значения равны."},
            {"value": "=", "error_logic": "Ученик округлил оба числа и назвал их равными."},
        ],
        question=question,
        correct_answer="<",
        answer_type="exact_number",
        min_count=2,
    )
    assert not stored_distractors_valid(
        [
            {"value": ">", "error_logic": "Ученик перепутал направление сравнения чисел."},
            {"value": "сравнить невозможно", "error_logic": "Ученик отказался сравнивать значения."},
        ],
        question=question,
        correct_answer="<",
        answer_type="exact_number",
        min_count=2,
    )


def test_exact_number_legacy_place_value_distractor_is_parseable():
    check = validate_distractor(
        question="До какого разряда округляют число?",
        value="до сотен",
        correct_answer="до тысяч",
        answer_type="exact_number",
        error_logic="Ученик округлил число на один разряд точнее, чем требовалось.",
        skip_l3=True,
    )
    assert check.ok, check.reason


def test_malformed_numeric_distractor_returns_parse_failed_not_exception():
    check = validate_distractor(
        question="Вычислите значение.",
        value="(",
        correct_answer="12",
        answer_type="exact_number",
        error_logic="Ученик не завершил вычисление и оставил незакрытую скобку.",
        skip_l3=True,
    )
    assert not check.ok
    assert check.reason == "parse_failed"


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


def test_reject_error_logic_with_impossible_digit_reversal():
    check = validate_distractor(
        question="Найдите исходное число.",
        value="27",
        correct_answer="37",
        answer_type="exact_number",
        error_logic=(
            "Ученик получил число 73, но затем переставил цифры местами, "
            "записав 27."
        ),
        skip_l3=True,
    )
    assert not check.ok
    assert check.reason == "implausible"


def test_accept_error_logic_with_actual_digit_reversal():
    check = validate_distractor(
        question="Найдите исходное число.",
        value="73",
        correct_answer="37",
        answer_type="exact_number",
        error_logic=(
            "Ученик получил число 37, но затем перепутал порядок цифр, "
            "записав 73."
        ),
        skip_l3=True,
    )
    assert check.ok


def test_reject_place_value_assignment_that_breaks_preceding_equation():
    check = validate_distractor(
        question="Найдите исходное число.",
        value="62",
        correct_answer="37",
        answer_type="exact_number",
        error_logic=(
            "Ученик получил 10a+b=18, затем подобрал a=6, b=2 и записал 62."
        ),
        skip_l3=True,
    )
    assert not check.ok
    assert check.reason == "implausible"
