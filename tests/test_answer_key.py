"""Раздел «Ответы»: разбор, выбор ключа join, приоритет книги (инвариант И2)."""

import pytest

from src.pipeline import answer_key as AK
from src.pipeline import provenance as prov
from src.pipeline.models import ExtractedTask


def task(number="", answer="", source=prov.ABSENT, paragraph="", atype="exact_number"):
    return ExtractedTask(
        exercise_number=number,
        paragraph_number=paragraph,
        answer_raw=answer,
        answer_source=source,
        answer_type=atype,
        question_text="Условие достаточной длины для гейта",
    )


class TestNormNumber:
    @pytest.mark.parametrize("raw,expected", [
        ("542.*", "542"),
        ("29.°", "29"),
        ("142а)", "142а"),
        ("  17 ", "17"),
        ("(8)", "8"),
        ("", ""),
        (None, ""),
    ])
    def test_edge_junk_stripped(self, raw, expected):
        assert AK.norm_number(raw) == expected

    def test_inner_dot_preserved(self):
        """«1.5» — номер, а не мусор: режем только края."""
        assert AK.norm_number("1.5") == "1.5"

    def test_case_folded(self):
        assert AK.norm_number("142А") == AK.norm_number("142а")


class TestIsEmptyAnswer:
    @pytest.mark.parametrize("v", ["", "  ", "—", "-", "?", "...", "…", None])
    def test_placeholders_are_empty(self, v):
        assert AK.is_empty_answer(v)

    def test_zero_is_a_real_answer(self):
        """«0» — валидный ответ, а не отсутствие ответа."""
        assert not AK.is_empty_answer("0")


class TestParseAnswerSection:
    def test_splits_dense_list(self):
        got = AK.parse_answer_section("54. 2) 90 книг. 55. б) 18 мест. 56. 80 орехов.", 93)
        assert [a["number"] for a in got] == ["54", "55", "56"]
        assert got[0]["answer_md"] == "2) 90 книг."
        assert all(a["source_page"] == 93 for a in got)

    def test_paren_form(self):
        got = AK.parse_answer_section("12) x = 5 13) y = 7")
        assert [a["number"] for a in got] == ["12", "13"]

    def test_empty_input(self):
        assert AK.parse_answer_section("") == []
        assert AK.parse_answer_section("   ") == []

    def test_letter_suffix_number(self):
        got = AK.parse_answer_section("142а. x=1")
        assert got[0]["number"] == "142а"


class TestJoinStrategy:
    def test_continuous_numbering_joins_by_number(self):
        tasks = [task(number=str(i)) for i in range(1, 51)]
        assert AK.choose_join_strategy(tasks) == AK.BY_NUMBER

    def test_reset_numbering_requires_paragraph(self):
        """ДТМ2020: 731 задача на 110 номеров — join по номеру запрещён."""
        tasks = [task(number=str(i % 10)) for i in range(100)]
        assert AK.choose_join_strategy(tasks) == AK.BY_PARAGRAPH_NUMBER

    def test_rare_duplicates_do_not_flip_strategy(self):
        """Единичный дубль — форматный мусор, а не сброс нумерации."""
        tasks = [task(number=str(i)) for i in range(100)] + [task(number="7")]
        assert AK.choose_join_strategy(tasks) == AK.BY_NUMBER

    def test_ratio_counts_tasks_not_distinct_numbers(self):
        # 3 различных дублирующихся номера, но под ними 90 из 93 задач.
        tasks = [task(number=str(i % 3)) for i in range(90)] + [
            task(number="A"), task(number="B"), task(number="C")
        ]
        assert AK.choose_join_strategy(tasks) == AK.BY_PARAGRAPH_NUMBER

    def test_no_numbers_at_all(self):
        assert AK.choose_join_strategy([task(), task()]) == AK.BY_NUMBER


class TestJoinAnswers:
    def test_exact_match_sets_book_source(self):
        tasks = [task(number="1"), task(number="2")]
        answers = [{"number": "1", "answer_md": "42", "source_page": 93}]
        rep = AK.join_answers(tasks, answers)
        assert rep.matched == 1
        assert tasks[0].answer_raw == "42"
        assert tasks[0].answer_source == prov.BOOK_KEY
        assert tasks[0].answer_source_page == 93
        assert tasks[1].answer_source == prov.ABSENT

    def test_book_answer_evicts_ai_answer(self):
        """И2: книжный ответ ВЫТЕСНЯЕТ придуманный моделью."""
        t = task(number="1", answer="неверно", source=prov.AI_SOLVED)
        rep = AK.join_answers([t], [{"number": "1", "answer_md": "42"}])
        assert rep.matched == 1
        assert t.answer_raw == "42"
        assert t.answer_source == prov.BOOK_KEY

    def test_book_answer_does_not_overwrite_book_answer(self):
        t = task(number="1", answer="исходный", source=prov.BOOK_KEY)
        rep = AK.join_answers([t], [{"number": "1", "answer_md": "другой"}])
        assert rep.skipped_outranked == 1
        assert t.answer_raw == "исходный"

    def test_ambiguous_number_is_refused_not_guessed(self):
        """Два задания под одним номером — ответ не достаётся ни одному."""
        tasks = [task(number="1"), task(number="1")] + [task(number=str(i)) for i in range(2, 40)]
        rep = AK.join_answers(tasks, [{"number": "1", "answer_md": "42"}])
        assert rep.matched == 0
        assert rep.ambiguous >= 2
        assert all(t.answer_raw == "" for t in tasks[:2])

    def test_duplicate_answers_counted_not_applied_twice(self):
        tasks = [task(number="1")]
        answers = [{"number": "1", "answer_md": "первый"}, {"number": "1", "answer_md": "второй"}]
        rep = AK.join_answers(tasks, answers)
        assert rep.dup_answers == 1
        assert tasks[0].answer_raw == "первый"

    def test_empty_answer_is_not_joined(self):
        t = task(number="1")
        rep = AK.join_answers([t], [{"number": "1", "answer_md": "—"}])
        assert rep.matched == 0
        assert t.answer_source == prov.ABSENT

    def test_unmatched_answers_reported(self):
        """Ответ есть, задачи нет — почти всегда дефект сегментации."""
        rep = AK.join_answers([task(number="1")], [{"number": "99", "answer_md": "42"}])
        assert rep.unmatched_answers == ["99"]

    def test_paragraph_strategy_requires_both_parts(self):
        tasks = [task(number="1", paragraph="§3"), task(number="1", paragraph="§7")]
        answers = [{"number": "1", "paragraph_number": "§7", "answer_md": "42"}]
        rep = AK.join_answers(tasks, answers, strategy=AK.BY_PARAGRAPH_NUMBER)
        assert rep.matched == 1
        assert tasks[0].answer_raw == ""   # §3 не получил чужой ответ
        assert tasks[1].answer_raw == "42"

    def test_join_is_idempotent(self):
        tasks = [task(number="1")]
        answers = [{"number": "1", "answer_md": "42"}]
        AK.join_answers(tasks, answers)
        rep2 = AK.join_answers(tasks, answers)
        assert rep2.matched == 0 and rep2.skipped_outranked == 1
        assert tasks[0].answer_raw == "42"

    def test_coverage_none_without_tasks(self):
        assert AK.join_answers([], []).coverage is None


class TestNeedsAiAnswer:
    def test_book_answer_blocks_the_model(self):
        assert not AK.needs_ai_answer(task(answer="42", source=prov.BOOK_KEY))

    def test_absent_answer_allows_the_model(self):
        assert AK.needs_ai_answer(task())

    def test_already_ai_solved_is_not_re_solved(self):
        assert not AK.needs_ai_answer(task(answer="7", source=prov.AI_SOLVED))


class TestMarkExisting:
    def test_answer_without_source_becomes_book_solution(self):
        t = task(answer="42")
        assert AK.mark_existing_answers([t]) == 1
        assert t.answer_source == prov.BOOK_SOLUTION

    def test_marking_does_not_touch_known_sources(self):
        t = task(answer="7", source=prov.AI_SOLVED)
        assert AK.mark_existing_answers([t]) == 0
        assert t.answer_source == prov.AI_SOLVED


class TestCoverageMetric:
    def test_counts_both_book_sources(self):
        tasks = [
            task(answer="1", source=prov.BOOK_KEY),
            task(answer="2", source=prov.BOOK_SOLUTION),
            task(answer="3", source=prov.AI_SOLVED),
            task(),
        ]
        assert AK.answer_join_coverage(tasks) == 0.5

    def test_empty_is_none(self):
        assert AK.answer_join_coverage([]) is None


class TestAnswerSeparatorChoice:
    """Разделитель выбирается по факту: точка и скобка значат разное."""

    def test_dot_book_ignores_subitem_parens(self):
        # Ровно строка из textzadachi5: 2) и 3) — подпункты ответа 56, не задачи.
        got = AK.parse_answer_section("56. 2) 80 и 40 орехов; 3) 44 страницы. 57. а) 36 тетрадей.")
        assert [a["number"] for a in got] == ["56", "57"]
        assert "3) 44 страницы." in got[0]["answer_md"]

    def test_paren_book_still_parses(self):
        got = AK.parse_answer_section("12) x = 5 13) y = 7 14) z = 9")
        assert [a["number"] for a in got] == ["12", "13", "14"]

    def test_single_dot_answer(self):
        assert AK.parse_answer_section("142а. x=1")[0]["number"] == "142а"

    def test_no_space_after_dot(self):
        # «60.1) 15 тетрадей» — подпункт вплотную к номеру задачи.
        got = AK.parse_answer_section("60.1) 15 тетрадей; 2) 30 тетрадей. 61.18 и 12 карандашей.")
        assert [a["number"] for a in got] == ["60", "61"]

    def test_monotonic_filter_drops_backward_jump(self):
        # Десятичная дробь внутри ответа не должна увести номер назад.
        got = AK.parse_answer_section("80. длина 2. 5 м. 81. ответ.")
        nums = [int(a["number"]) for a in got]
        assert nums == sorted(nums), "номера обязаны идти по возрастанию"
        assert nums[0] == 80


class TestSubtaskJoin:
    """Извлечение делит задачу книги на подпункты — join обязан это учитывать."""

    def test_split_number_sub(self):
        assert AK.split_number_sub("43.а") == ("43", "а")
        assert AK.split_number_sub("46.1") == ("46", "1")
        assert AK.split_number_sub("45") == ("45", "")

    def test_labeled_answer_parts(self):
        parts = AK.split_labeled_answer("а) 215 мужских часов; б) 265 т.")
        assert parts["а"] == "215 мужских часов"
        assert parts["б"] == "265 т"

    def test_answer_for_subtask_picks_its_part(self):
        whole = "а) 215 мужских часов; б) 265 т."
        assert AK.answer_for_subtask(whole, "б") == "265 т"

    def test_unlabeled_answer_goes_whole(self):
        assert AK.answer_for_subtask("56 книг", "") == "56 книг"

    def test_missing_label_yields_nothing(self):
        # Книга печатает «2. б) 76 страниц.» — части «а)» просто нет.
        # Отдать сюда весь ответ значит выдать 2.а ответ, принадлежащий 2.б.
        assert AK.answer_for_subtask("б) 76 страниц.", "а") == ""

    def test_unlabeled_answer_applies_to_any_subtask(self):
        assert AK.answer_for_subtask("56 книг", "а") == "56 книг"

    def test_subtask_without_printed_answer_is_not_joined(self):
        t = ExtractedTask(exercise_number="2.а", question_text="…",
                          answer_raw="12", answer_source=prov.AI_SOLVED,
                          answer_type="text")
        report = AK.join_answers([t], [{"number": "2", "answer_md": "б) 76 страниц.",
                                        "source_page": 92}])
        assert report.matched == 0
        assert t.answer_source == prov.AI_SOLVED, "ответ модели остаётся, но помеченным"
        assert t.answer_raw == "12"

    def test_subtasks_join_to_their_parts(self):
        a = ExtractedTask(exercise_number="43.а", question_text="…", answer_type="text")
        b = ExtractedTask(exercise_number="43.б", question_text="…", answer_type="text")
        answers = [{"number": "43", "answer_md": "а) 215 мужских часов; б) 265 т.",
                    "source_page": 93}]
        report = AK.join_answers([a, b], answers)
        assert report.matched == 2
        assert a.answer_raw == "215 мужских часов"
        assert b.answer_raw == "265 т"
        assert a.answer_source == prov.BOOK_KEY

    def test_subtasks_are_not_treated_as_duplicate_numbers(self):
        # «43.а» и «43.б» — одна задача книги, а не два конфликтующих номера.
        tasks = [
            ExtractedTask(exercise_number="43.а", question_text="…"),
            ExtractedTask(exercise_number="43.б", question_text="…"),
        ]
        assert AK.duplicate_numbers(tasks) == set()


class TestSubtasksDoNotDisableTheGuard:
    """B38: подпункты обходили с фланга обе защиты И2 сразу.

    `duplicate_numbers` пропускала записи с подпунктом (`if sub: continue`), а
    от неё зависят и выбор стратегии в `choose_join_strategy`, и поштучный
    отказ в `join_answers`. У книги со сбросом нумерации, чьи задачи разложены
    на «43.а/43.б», множество дублей выходило пустым — стратегия выбиралась
    `number`, отказов не было ни одного, и §7 №43.а получал ответ от §3
    с пометкой `book_key` и `confidence.answer = 1.0`.
    """

    def test_same_number_in_two_paragraphs_is_ambiguous(self):
        tasks = [
            task(number="43", paragraph="3"),
            task(number="43.а", paragraph="7"),
            task(number="43.б", paragraph="7"),
        ]
        assert AK.duplicate_numbers(tasks) == {"43"}

    def test_subparts_of_one_task_stay_unambiguous(self):
        tasks = [
            task(number="43.а", paragraph="7"),
            task(number="43.б", paragraph="7"),
            task(number="43.в", paragraph="7"),
        ]
        assert AK.duplicate_numbers(tasks) == set()

    def test_two_whole_tasks_in_one_paragraph_are_ambiguous(self):
        # Дефект сегментации: одно упражнение разбито на две записи целиком.
        tasks = [task(number="43", paragraph="7"), task(number="43", paragraph="7")]
        assert AK.duplicate_numbers(tasks) == {"43"}

    def test_reset_numbering_with_subparts_picks_paragraph_strategy(self):
        # Было: `number`, потому что дублей «не находилось».
        tasks = [
            task(number=f"{n}.{sub}", paragraph=str(para))
            for para in range(1, 11)
            for n in range(1, 6)
            for sub in ("а", "б")
        ]
        assert AK.choose_join_strategy(tasks) == AK.BY_PARAGRAPH_NUMBER

    def test_answer_does_not_travel_to_another_paragraph(self):
        """Контроль всей цепочки: чужой ответ не должен доехать и провенанс
        не должен его подтвердить."""
        p3 = task(number="43", paragraph="3", atype="text")
        p7a = task(number="43.а", paragraph="7", atype="text")
        p7b = task(number="43.б", paragraph="7", atype="text")
        answers = [{"number": "43", "answer_md": "а) 215; б) 265", "source_page": 200}]

        report = AK.join_answers([p3, p7a, p7b], answers, strategy=AK.BY_NUMBER)

        assert report.matched == 0
        for t in (p3, p7a, p7b):
            assert t.answer_raw == ""
            assert t.answer_source == prov.ABSENT
            assert (t.confidence or {}).get("answer") is None

    def test_book_answer_outranks_model_answer(self):
        t = ExtractedTask(exercise_number="43.а", question_text="…",
                          answer_raw="215", answer_source=prov.AI_SOLVED,
                          answer_type="text")
        AK.join_answers([t], [{"number": "43", "answer_md": "а) 215 мужских часов",
                               "source_page": 93}])
        assert t.answer_source == prov.BOOK_KEY
        assert t.answer_raw == "215 мужских часов"
