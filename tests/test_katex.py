"""Тесты компиляции формул через KaTeX (Сессия 2).

Требуют Node + npm-пакет `katex` (`npm install`). CI их не ставит, поэтому
тесты пропускаются, а не падают — отсутствие KaTeX не должно ломать сборку.
"""
from __future__ import annotations

import pytest

from src.validate import katex
from src.validate.latex_artifacts import repair

pytestmark = pytest.mark.skipif(
    not katex.is_available(), reason="нет node или npm-пакета katex (npm install)"
)


def test_empty_input_no_subprocess():
    assert katex.compile_formulas([]) == []
    assert katex.compile_with_errors([]) == []


def test_valid_formulas_compile():
    assert katex.compile_formulas([r"x^2-5x+6=0", r"\dfrac{a}{b}", r"\sqrt{2}"]) == [
        True,
        True,
        True,
    ]


def test_cyrillic_inside_text_compiles():
    # кириллица в \text — законна, не должна считаться поломкой
    assert katex.compile_formulas([r"S_{\text{общ}}"]) == [True]


def test_broken_formulas_flagged():
    broken = [r"\frac{1}{2", r"\unknowncmd{x}", "\\left(\\frac{14\\pi}{3}ight)"]
    assert katex.compile_formulas(broken) == [False, False, False]


def test_error_messages_present():
    res = katex.compile_with_errors([r"\frac{1}{2"])
    assert res[0]["ok"] is False
    assert "KaTeX parse error" in res[0]["error"]


def test_order_preserved_across_batches():
    formulas = ["x^2"] * 3 + [r"\frac{1}{2"] + ["y^2"] * 2
    assert katex.compile_formulas(formulas, batch_size=2) == [
        True, True, True, False, True, True,
    ]


def test_repair_makes_broken_formulas_compile():
    """Round-trip: детерминированный ремонт восстанавливает компилируемость."""
    broken = ["\\left(\\frac{14\\pi}{3}ight)", "150^\\\\circ"]
    assert katex.compile_formulas(broken) == [False, False]
    assert katex.compile_formulas([repair(b) for b in broken]) == [True, True]
