"""Селективный консенсус (инвариант И5): маршрутизатор, а не сертификат."""

import pytest

from src.pipeline import consensus as C
from src.pipeline import gates as G
from src.pipeline import provenance as prov
from src.pipeline.models import ExtractedTask


def task(**kw):
    base = dict(
        question_text="Вычислите площадь круга радиуса пять",
        answer_raw="42",
        answer_source=prov.BOOK_KEY,
        answer_type="exact_number",
    )
    base.update(kw)
    return ExtractedTask(**base)


class TestTriggers:
    def test_clean_book_task_needs_no_second_pass(self):
        need, why = C.should_consensus(task(), G.Verdict())
        assert need is False and why == []

    def test_artifacts_trigger(self):
        v = G.Verdict(artifacts=["потерян \\ в \\frac"])
        need, why = C.should_consensus(task(), v)
        assert need and "артефакты LaTeX в извлечении" in why

    def test_broken_formula_triggers(self):
        need, _ = C.should_consensus(task(), G.Verdict(formulas_broken=2))
        assert need

    def test_ai_answer_triggers(self):
        need, why = C.should_consensus(task(answer_source=prov.AI_SOLVED), G.Verdict())
        assert need and "ответ придуман моделью" in why

    def test_missing_answer_triggers(self):
        need, _ = C.should_consensus(task(answer_raw=""), G.Verdict())
        assert need

    def test_text_type_without_answer_does_not_trigger(self):
        need, _ = C.should_consensus(
            task(answer_raw="", answer_type="open_text"), G.Verdict()
        )
        assert not need

    def test_numbering_gap_triggers(self):
        need, why = C.should_consensus(task(), G.Verdict(), paragraph_has_gap=True)
        assert need and "дыра в нумерации параграфа" in why

    def test_works_without_a_verdict(self):
        need, _ = C.should_consensus(task())
        assert need is False


class TestGappedParagraphs:
    def test_finds_the_hole(self):
        tasks = [
            ExtractedTask(exercise_number=n, paragraph_number="§1")
            for n in ("1", "2", "4")
        ]
        assert C.gapped_paragraphs(tasks) == {"§1"}

    def test_continuous_has_no_gap(self):
        tasks = [
            ExtractedTask(exercise_number=n, paragraph_number="§1")
            for n in ("1", "2", "3")
        ]
        assert C.gapped_paragraphs(tasks) == set()

    def test_gap_is_scoped_to_its_paragraph(self):
        """Нумерация сбрасывается в каждом параграфе — дыры не смешиваются."""
        tasks = [
            ExtractedTask(exercise_number="1", paragraph_number="§1"),
            ExtractedTask(exercise_number="2", paragraph_number="§1"),
            ExtractedTask(exercise_number="1", paragraph_number="§2"),
            ExtractedTask(exercise_number="3", paragraph_number="§2"),
        ]
        assert C.gapped_paragraphs(tasks) == {"§2"}


class TestComparePasses:
    def test_unanimous(self):
        r = C.compare_passes(["x = 5", "x = 5", "x = 5"])
        assert r.unanimous and r.agreement == 1.0 and not r.disagreed

    def test_formatting_differences_are_not_disagreement(self):
        """Канонизация обязательна: иначе настоящие расхождения утонут в шуме."""
        r = C.compare_passes([r"$\dfrac{1}{2}$", r"$\frac{1}{2}$", r"$ \frac{1}{2} $"])
        assert r.unanimous

    def test_real_disagreement_detected(self):
        r = C.compare_passes(["x = 5", "x = 5", "x = 7"])
        assert r.disagreed
        assert r.majority_count == 2
        assert round(r.agreement, 2) == 0.67

    def test_single_pass_is_not_disagreement(self):
        assert not C.compare_passes(["x = 5"]).disagreed

    def test_all_empty(self):
        r = C.compare_passes(["", "  "])
        assert r.agreement is None and r.majority is None


class TestRouting:
    def test_disagreement_routes_to_review(self):
        t, v = task(), G.Verdict()
        C.route(t, v, C.compare_passes(["x=5", "x=7"]))
        assert v.status == G.REVIEW

    def test_agreement_does_not_certify(self):
        """Сердцевина И5: согласие НЕ повышает вердикт до pass."""
        t = task(question_text="Реши")
        v = G.Verdict()
        G.check_structure(t, v)
        assert v.status == G.REJECT
        C.route(t, v, C.compare_passes(["x=5", "x=5", "x=5"]))
        assert v.status == G.REJECT

    def test_agreement_only_records_confidence(self):
        t, v = task(), G.Verdict()
        C.route(t, v, C.compare_passes(["x=5", "x=5"]))
        assert v.status == G.PASS
        assert t.confidence["consensus"] == 1.0
        assert v.reasons == []

    def test_unanimous_does_not_rescue_a_review(self):
        t = task(answer_source=prov.AI_SOLVED)
        v = G.Verdict()
        G.check_provenance(t, v)
        assert v.status == G.REVIEW
        C.route(t, v, C.compare_passes(["7", "7", "7"]))
        assert v.status == G.REVIEW
