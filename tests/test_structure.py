"""Структурный слой: общий контекст, склейка через разрыв, порядок (Сессия 4).

Синтетические кейсы: каждый воспроизводит конкретный дефект вёрстки, ради
которого модуль и существует.
"""

import pytest

from src.pipeline import structure as S
from src.pipeline.models import ExtractedTask


def task(num="", text="Условие задачи.", page=1, para="§1", ctx="", latex=""):
    return ExtractedTask(
        exercise_number=num, question_text=text, page=page,
        paragraph_number=para, shared_context=ctx, question_latex=latex,
    )


class TestParseRange:
    def test_plain_range(self):
        assert S.parse_range("В задачах 140–145 решите уравнение:") == (140, 145)

    def test_hyphen_and_emdash(self):
        assert S.parse_range("Задачи 3-7") == (3, 7)
        assert S.parse_range("Задачи 3—7") == (3, 7)

    def test_reversed_range_normalised(self):
        assert S.parse_range("В задачах 145–140") == (140, 145)

    def test_exercises_wording(self):
        assert S.parse_range("В упражнениях 10–12 упростите") == (10, 12)

    def test_no_range(self):
        assert S.parse_range("Решите уравнение:") is None
        assert S.parse_range("") is None


class TestIsSharedInstruction:
    def test_imperative_is_instruction(self):
        assert S.is_shared_instruction("Решите уравнения:")
        assert S.is_shared_instruction("Упростите выражение:")

    def test_range_is_instruction(self):
        assert S.is_shared_instruction("В задачах 140–145:")

    def test_uzbek_imperative(self):
        assert S.is_shared_instruction("Hisoblang:")

    def test_section_title_is_not(self):
        # Ровно то ложное срабатывание, ради которого нужна чистка.
        assert not S.is_shared_instruction("Алгебраические выражения")
        assert not S.is_shared_instruction("Глава 3. Квадратные уравнения")

    def test_empty(self):
        assert not S.is_shared_instruction("")
        assert not S.is_shared_instruction(None)


class TestSharedContext:
    def test_false_context_cleaned(self):
        t = task(num="1", ctx="Алгебраические выражения")
        stats = S.apply_shared_context([t])
        assert t.shared_context == ""
        assert stats["cleaned"] == 1

    def test_real_instruction_kept(self):
        t = task(num="1", ctx="Решите уравнения:")
        S.apply_shared_context([t])
        assert t.shared_context == "Решите уравнения:"

    def test_range_propagates_to_members(self):
        src = task(num="140", ctx="В задачах 140–142 решите уравнение:")
        mid = task(num="141")
        last = task(num="142")
        outside = task(num="143")
        stats = S.apply_shared_context([src, mid, last, outside])
        assert mid.shared_context == src.shared_context
        assert last.shared_context == src.shared_context
        assert outside.shared_context == ""
        assert stats["propagated"] == 2

    def test_does_not_cross_paragraph(self):
        src = task(num="140", para="§1", ctx="В задачах 140–142 решите:")
        other = task(num="141", para="§2")
        S.apply_shared_context([src, other])
        assert other.shared_context == ""

    def test_existing_context_not_overwritten(self):
        src = task(num="140", ctx="В задачах 140–142 решите уравнение:")
        own = task(num="141", ctx="Упростите:")
        S.apply_shared_context([src, own])
        assert own.shared_context == "Упростите:"


class TestMergePageBreaks:
    def test_merges_tail_without_number(self):
        head = task(num="12", text="Найдите значение выражения, если", page=7)
        tail = task(num="", text="a = 3 и b = 5.", page=8)
        out, merged = S.merge_page_breaks([head, tail])
        assert merged == 1
        assert len(out) == 1
        assert out[0].question_text == "Найдите значение выражения, если a = 3 и b = 5."
        assert "merged_across_pages" in out[0].review_flags

    def test_finished_statement_not_merged(self):
        head = task(num="12", text="Решите уравнение.", page=7)
        tail = task(num="", text="Продолжение.", page=8)
        out, merged = S.merge_page_breaks([head, tail])
        assert merged == 0 and len(out) == 2

    def test_numbered_fragment_is_new_task(self):
        head = task(num="12", text="Найдите значение, если", page=7)
        nxt = task(num="13", text="Решите уравнение.", page=8)
        out, merged = S.merge_page_breaks([head, nxt])
        assert merged == 0 and len(out) == 2

    def test_distant_pages_not_merged(self):
        head = task(num="12", text="Найдите значение, если", page=7)
        tail = task(num="", text="a = 3.", page=20)
        out, merged = S.merge_page_breaks([head, tail])
        assert merged == 0 and len(out) == 2

    def test_not_merged_across_paragraphs(self):
        head = task(num="12", text="Найдите значение, если", page=7, para="§1")
        tail = task(num="", text="a = 3.", page=8, para="§2")
        out, merged = S.merge_page_breaks([head, tail])
        assert merged == 0 and len(out) == 2

    def test_figure_refs_carried_over(self):
        head = task(num="12", text="Найдите площадь фигуры на", page=7)
        tail = task(num="", text="рисунке 4.", page=8)
        tail.figure_refs = ["fig-p8-1"]
        out, _ = S.merge_page_breaks([head, tail])
        assert out[0].figure_refs == ["fig-p8-1"]

    def test_colon_is_not_terminal(self):
        head = task(num="12", text="Решите уравнения:", page=7)
        tail = task(num="", text="x² − 9 = 0.", page=8)
        out, merged = S.merge_page_breaks([head, tail])
        assert merged == 1

    def test_empty_input(self):
        assert S.merge_page_breaks([]) == ([], 0)


class TestOrdering:
    def test_two_column_scramble_restored(self):
        tasks = [task(num=n) for n in ("1", "4", "2", "5", "3", "6")]
        out, reordered = S.order_within_paragraphs(tasks)
        assert [t.exercise_number for t in out] == ["1", "2", "3", "4", "5", "6"]
        assert reordered == 1

    def test_letter_suffix_sorts_after_bare_number(self):
        tasks = [task(num="142б"), task(num="142"), task(num="142а")]
        out, _ = S.order_within_paragraphs(tasks)
        assert [t.exercise_number for t in out] == ["142", "142а", "142б"]

    def test_paragraph_boundary_not_crossed(self):
        tasks = [task(num="5", para="§1"), task(num="1", para="§2")]
        out, _ = S.order_within_paragraphs(tasks)
        assert [t.paragraph_number for t in out] == ["§1", "§2"]

    def test_unnumbered_task_is_anchor(self):
        anchor = task(num="", text="Вводная врезка.")
        tasks = [task(num="3"), anchor, task(num="2"), task(num="1")]
        out, _ = S.order_within_paragraphs(tasks)
        assert out[1] is anchor
        assert [t.exercise_number for t in out] == ["3", "", "1", "2"]

    def test_already_ordered_reports_zero(self):
        tasks = [task(num=n) for n in ("1", "2", "3")]
        _, reordered = S.order_within_paragraphs(tasks)
        assert reordered == 0


class TestApplyAll:
    def test_pipeline_order_merge_before_sort(self):
        # Хвост без номера идёт после задачи 4; если отсортировать ДО склейки,
        # он уедет в конец и голова останется обрывком.
        tasks = [
            task(num="1", text="Решите уравнение.", page=1),
            task(num="4", text="Найдите значение, если", page=1),
            task(num="", text="a = 2.", page=2),
            task(num="2", text="Упростите выражение.", page=2),
        ]
        out, summary = S.apply(tasks)
        assert summary["merged"] == 1
        texts = {t.exercise_number: t.question_text for t in out}
        assert texts["4"] == "Найдите значение, если a = 2."
        assert [t.exercise_number for t in out] == ["1", "2", "4"]

    def test_empty_input_returns_zero_summary(self):
        out, summary = S.apply([])
        assert out == []
        assert summary == {
            "cleaned": 0, "propagated": 0, "merged": 0, "reordered": 0,
            "numbering_gaps": 0,
        }
