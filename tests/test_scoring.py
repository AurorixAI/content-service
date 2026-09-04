"""Доверие и очередь ручной проверки (Сессия 5), включая регрессию на B1."""

import pytest

from src.pipeline import gates as G
from src.pipeline import provenance as prov
from src.pipeline import scoring as SC
from src.pipeline.models import ExtractedTask


def task(text="Вычислите площадь круга радиуса пять", answer="42",
         source=prov.BOOK_KEY, options=None, flags=None, latex=""):
    t = ExtractedTask(
        question_text=text, answer_raw=answer, answer_source=source,
        answer_type="exact_number", question_latex=latex,
    )
    t.answer_options = options
    t.review_flags = list(flags or [])
    return t


def verdict(status=G.PASS, checked=0, broken=0, artifacts=(), measured=True):
    v = G.Verdict(status=status, formulas_checked=checked, formulas_broken=broken,
                  compile_measured=measured)
    v.artifacts = list(artifacts)
    return v


class TestB1EmptyStatement:
    """B1: пустое условие при непустых подпунктах — законный формат книги."""

    def test_empty_statement_without_subparts_is_zero(self):
        assert SC.score_structure(task(text="")) == 0.0

    def test_empty_statement_with_subparts_is_not_penalised_to_zero(self):
        t = task(text="", options=["а) x² − 9 = 0", "б) x² − 4 = 0"])
        assert SC.score_structure(t) > 0.0

    def test_subparts_task_does_not_trip_review(self):
        t = task(text="", options=["а) 2", "б) 3"])
        conf = prov.Confidence(ocr=None, structure=SC.score_structure(t), answer=1.0)
        assert not SC.needs_review(t, verdict(), conf)

    def test_full_statement_is_one(self):
        assert SC.score_structure(task()) == 1.0

    def test_numbering_gap_lowers_structure(self):
        t = task(flags=[SC.NUMBERING_GAP_FLAG])
        assert SC.score_structure(t) == 0.5


class TestScoreOcr:
    def test_all_formulas_compile(self):
        assert SC.score_ocr(task(), verdict(checked=4, broken=0)) == 1.0

    def test_broken_formulas_lower_score(self):
        assert SC.score_ocr(task(), verdict(checked=4, broken=2)) == 0.5

    def test_not_measured_is_none_not_zero(self):
        # Нет Node и нет других сигналов: «не измерено» ≠ «плохо».
        assert SC.score_ocr(task(), verdict(measured=False)) is None

    def test_artifacts_penalise_even_when_compiling(self):
        # Артефакты компиляция не видит — иначе они бы прошли молча.
        v = verdict(checked=2, broken=0, artifacts=["double_backslash"])
        assert SC.score_ocr(task(), v) < 1.0

    def test_unreadable_marker_caps_score(self):
        t = task(text=f"Вычислите {SC.UNREADABLE} площадь")
        assert SC.score_ocr(t, verdict(checked=2, broken=0)) <= SC._UNREADABLE_CAP

    def test_score_stays_in_range(self):
        v = verdict(checked=1, broken=1, artifacts=["a", "b", "c", "d", "e"])
        s = SC.score_ocr(task(), v)
        assert 0.0 <= s <= 1.0


class TestScoreAnswer:
    def test_book_key_is_highest(self):
        assert SC.score_answer(task(source=prov.BOOK_KEY)) == 1.0

    def test_ai_solved_is_low(self):
        assert SC.score_answer(task(source=prov.AI_SOLVED)) == 0.40

    def test_absent_is_none(self):
        assert SC.score_answer(task(source=prov.ABSENT)) is None

    def test_book_outranks_ai(self):
        assert SC.score_answer(task(source=prov.BOOK_KEY)) > SC.score_answer(
            task(source=prov.AI_SOLVED)
        )


class TestNeedsReview:
    def test_clean_task_passes(self):
        t = task()
        conf = prov.Confidence(ocr=1.0, structure=1.0, answer=1.0)
        assert not SC.needs_review(t, verdict(), conf)

    def test_reject_verdict_forces_review(self):
        conf = prov.Confidence(ocr=1.0, structure=1.0, answer=1.0)
        assert SC.needs_review(task(), verdict(status=G.REJECT), conf)

    def test_bare_review_without_quality_signal_does_not_flag(self):
        # `review` из-за отсутствия ответа — вопрос полноты, а не качества.
        # Если он попадает в очередь, туда попадает вся книга и очередь
        # перестаёт что-либо приоритизировать.
        conf = prov.Confidence(ocr=1.0, structure=1.0, answer=None)
        assert not SC.needs_review(task(), verdict(status=G.REVIEW), conf)

    def test_single_broken_formula_forces_review(self):
        conf = prov.Confidence(ocr=1.0, structure=1.0, answer=1.0)
        assert SC.needs_review(task(), verdict(checked=9, broken=1), conf)

    def test_unmeasured_confidence_does_not_force_review(self):
        conf = prov.Confidence(ocr=None, structure=1.0, answer=None)
        assert not SC.needs_review(task(), verdict(), conf)


class TestAwaitingAnswer:
    """Полнота отделена от качества, но не потеряна."""

    def test_absent_answer_is_awaiting(self):
        assert SC.awaiting_answer(task(source=prov.ABSENT))

    def test_ai_answer_is_awaiting(self):
        assert SC.awaiting_answer(task(source=prov.AI_SOLVED))

    def test_book_answer_is_not_awaiting(self):
        assert not SC.awaiting_answer(task(source=prov.BOOK_KEY))

    def test_counted_in_summary(self):
        tasks = [task(source=prov.ABSENT), task(source=prov.BOOK_KEY)]
        summary = SC.score_tasks(tasks, [verdict(), verdict()])
        assert summary["n_awaiting_answer"] == 1

    def test_awaiting_alone_keeps_queue_empty(self):
        tasks = [task(source=prov.ABSENT) for _ in range(5)]
        vs = [verdict(status=G.REVIEW) for _ in range(5)]
        summary = SC.score_tasks(tasks, vs)
        assert summary["n_needs_review"] == 0
        assert summary["n_awaiting_answer"] == 5


class TestScoreTasksAndQueue:
    def test_confidence_written_onto_task(self):
        t = task()
        SC.score_tasks([t], [verdict(checked=2, broken=0)])
        assert set(t.confidence) == {"ocr", "structure", "answer"}

    def test_summary_counts_review(self):
        good, bad = task(), task(text="")
        summary = SC.score_tasks([good, bad], [verdict(), verdict(status=G.REJECT)])
        assert summary["n_tasks"] == 2
        assert summary["n_needs_review"] == 1
        assert summary["review_rate"] == 0.5

    def test_flag_added_once(self):
        t = task(text="")
        vs = [verdict(status=G.REJECT)]
        SC.score_tasks([t], vs)
        SC.score_tasks([t], vs)
        assert t.review_flags.count("needs_review") == 1

    def test_queue_worst_first(self):
        clean = task()
        broken = task(text="")
        tasks = [clean, broken]
        vs = [verdict(), verdict(status=G.REJECT)]
        SC.score_tasks(tasks, vs)
        assert SC.review_queue(tasks, vs)[0] is broken

    def test_mismatched_lengths_rejected(self):
        with pytest.raises(AssertionError):
            SC.score_tasks([task()], [])
