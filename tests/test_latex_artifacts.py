"""Тесты детектора/ремонта OCR-артефактов бэкслеша (Сессия 2, B5).

Ключевой мотив: часть этих артефактов компилируется без ошибки, поэтому
гейта KaTeX недостаточно — см. докстринг `src/validate/latex_artifacts.py`.
"""
from __future__ import annotations

import pytest

from src.validate.latex_artifacts import (
    find_artifacts,
    has_artifacts,
    repair,
    repair_report,
)


# ── потерянный ведущий бэкслеш ────────────────────────────────────────────
@pytest.mark.parametrize(
    "broken,fixed",
    [
        ("rac{1}{2}", r"\frac{1}{2}"),
        (r"\left(\frac{14\pi}{3}ight)", r"\left(\frac{14\pi}{3}\right)"),
        ("eft( x \\right)", r"\left( x \right)"),
        ("ight]", r"\right]"),
    ],
)
def test_lost_backslash_detected_and_repaired(broken, fixed):
    assert has_artifacts(broken)
    assert repair(broken) == fixed


def test_lost_backslash_not_flagged_when_correct():
    assert find_artifacts(r"\frac{1}{2}") == []
    assert find_artifacts(r"\left( x \right)") == []
    assert find_artifacts(r"\sqrt{2}") == []


def test_ordinary_words_not_flagged():
    # «rac»/«ight»/«eft» как часть обычного текста — не артефакт.
    # Триггерит только характерный контекст (скобка/фигурная сразу после).
    assert find_artifacts("Найдите bracket и right угол") == []
    assert find_artifacts(r"\text{straight)}") == []


# ── задвоенный бэкслеш ────────────────────────────────────────────────────
def test_doubled_backslash_detected_and_repaired():
    assert has_artifacts("150^\\\\circ")
    assert repair("150^\\\\circ") == "150^\\circ"
    assert repair("x^2 \\\\cdot y") == "x^2 \\cdot y"


def test_doubled_backslash_silently_compiles_case():
    # именно тот случай, который KaTeX пропускает как валидный перенос строки
    src = "x^2 \\\\cdot y"
    assert has_artifacts(src), "детектор обязан ловить то, что компиляция пропускает"


def test_linebreak_in_matrix_not_flagged():
    # настоящий перенос строки не липнет к имени команды — не трогаем
    src = r"\begin{matrix} a & b \\ c & d \end{matrix}"
    assert find_artifacts(src) == []
    assert repair(src) == src


# ── общие свойства ────────────────────────────────────────────────────────
def test_repair_is_idempotent():
    src = "rac{1}{2} и 90^\\\\circ"
    once = repair(src)
    assert repair(once) == once


def test_clean_latex_untouched():
    for src in (r"x^2-5x+6=0", r"S_{\text{общ}}", r"\dfrac{a}{b}", ""):
        assert repair(src) == src
        assert find_artifacts(src) == []


def test_repair_report_lists_what_was_broken():
    fixed, issues = repair_report("rac{1}{2}")
    assert fixed == r"\frac{1}{2}"
    assert issues and "frac" in issues[0]


def test_empty_and_none_safe():
    assert find_artifacts("") == []
    assert find_artifacts(None) == []  # type: ignore[arg-type]
    assert repair(None) is None  # type: ignore[arg-type]
