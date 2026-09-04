"""Провенанс и порядок авторитета источников (инварианты И1/И2)."""

import pytest

from src.pipeline import provenance as prov


class TestAuthorityOrder:
    def test_book_outranks_everything_generated(self):
        for weaker in (prov.SYMPY_DERIVED, prov.AI_SOLVED, prov.ABSENT):
            assert prov.outranks(prov.BOOK_KEY, weaker)
            assert not prov.outranks(weaker, prov.BOOK_KEY)

    def test_ai_never_outranks_a_book_source(self):
        """Сердцевина И2: сгенерированное не перекрывает напечатанное."""
        assert not prov.outranks(prov.AI_SOLVED, prov.BOOK_KEY)
        assert not prov.outranks(prov.AI_SOLVED, prov.BOOK_SOLUTION)

    def test_ai_outranks_only_absence(self):
        assert prov.outranks(prov.AI_SOLVED, prov.ABSENT)

    def test_sympy_sits_between_book_and_ai(self):
        assert prov.outranks(prov.BOOK_SOLUTION, prov.SYMPY_DERIVED)
        assert prov.outranks(prov.SYMPY_DERIVED, prov.AI_SOLVED)

    def test_unknown_source_is_worse_than_any_known(self):
        """Неизвестный источник не должен случайно выиграть у известного."""
        assert not prov.outranks("что-то новое", prov.ABSENT)

    def test_order_is_strict(self):
        ranks = [prov.answer_rank(s) for s in prov.ANSWER_AUTHORITY]
        assert ranks == sorted(ranks)
        assert len(set(ranks)) == len(ranks)


class TestFromBook:
    def test_both_book_sources_count_as_book(self):
        assert prov.is_from_book(prov.BOOK_KEY)
        assert prov.is_from_book(prov.BOOK_SOLUTION)

    def test_generated_is_not_book(self):
        for s in (prov.SYMPY_DERIVED, prov.AI_SOLVED, prov.ABSENT):
            assert not prov.is_from_book(s)

    def test_ai_and_absent_need_human(self):
        assert prov.AI_SOLVED in prov.NEEDS_HUMAN
        assert prov.ABSENT in prov.NEEDS_HUMAN
        assert prov.BOOK_KEY not in prov.NEEDS_HUMAN


class TestConfidence:
    def test_unmeasured_is_none_not_zero(self):
        """«Не измеряли» нельзя путать с «измерили и ноль» — правило из С1."""
        c = prov.Confidence()
        assert c.ocr is None
        assert c.min_measured() is None

    def test_zero_is_a_measurement(self):
        c = prov.Confidence(answer=0.0)
        assert c.min_measured() == 0.0

    def test_from_dict_ignores_junk(self):
        c = prov.Confidence.from_dict({"ocr": "высокая", "structure": 0.9})
        assert c.ocr is None
        assert c.structure == 0.9

    def test_from_dict_rejects_bool(self):
        assert prov.Confidence.from_dict({"ocr": True}).ocr is None

    def test_from_dict_survives_non_dict(self):
        assert prov.Confidence.from_dict(None).as_dict() == {
            "ocr": None, "structure": None, "answer": None
        }

    def test_min_over_measured_only(self):
        c = prov.Confidence(ocr=0.8, answer=0.4)
        assert c.min_measured() == 0.4


def test_provenance_round_trips_to_dict():
    p = prov.Provenance(
        answer_source=prov.BOOK_KEY,
        confidence=prov.Confidence(ocr=1.0),
        answer_source_page=93,
    )
    d = p.as_dict()
    assert d["answer_source"] == "book_key"
    assert d["answer_source_page"] == 93
    assert d["confidence"]["ocr"] == 1.0
