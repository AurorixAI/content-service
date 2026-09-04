"""Тесты канонизации LaTeX — фундамент всех метрик (Сессия 1).

Перенесены из прототипа mathocr (`tests/test_canonical.py`) и расширены
кейсами, специфичными для нашего банка (кириллица внутри формул).
"""
from __future__ import annotations

from src.eval.canonical import (
    canonicalize,
    extract_formulas,
    extract_formulas_raw,
    strip_math_delimiters,
)


def test_dfrac_tfrac_to_frac():
    assert canonicalize(r"\dfrac{a}{b}") == r"\frac{a}{b}"
    assert canonicalize(r"\tfrac{1}{2}") == r"\frac{1}{2}"


def test_left_right_stripped():
    assert canonicalize(r"\left( x \right)") == "(x)"
    assert canonicalize(r"\left[ a \right]") == "[a]"


def test_cdot_to_star():
    assert canonicalize(r"a \cdot b") == "a*b"


def test_mathrm_unified_with_text():
    assert canonicalize(r"\mathrm{cm}") == canonicalize(r"\text{cm}") == r"\text{cm}"


def test_whitespace_removed():
    # пробел вокруг операторов — косметика, метрика не должна за неё штрафовать
    assert canonicalize("x^2   -   5x  +  6") == "x^2-5x+6"
    assert canonicalize("  a + b  ") == "a+b"
    assert canonicalize("25^{15} + 16^{27}") == "25^{15}+16^{27}"


def test_equivalent_forms_converge():
    a = canonicalize(r"\dfrac{1}{2} \cdot \left( x \right)")
    b = canonicalize(r"\frac{1}{2} * ( x )")
    assert a == b


def test_cyrillic_inside_formula_survives():
    # кириллица внутри формул — известное больное место, канонизация не должна её ломать
    assert canonicalize(r"S_{\text{общ}}") == r"S_{\text{общ}}"
    assert canonicalize(r"\mathrm{общ}") == r"\text{общ}"


def test_empty_and_none_safe():
    assert canonicalize("") == ""
    assert canonicalize(None) == ""  # type: ignore[arg-type]
    assert extract_formulas_raw(None) == []  # type: ignore[arg-type]


def test_strip_delimiters():
    assert strip_math_delimiters("$x+1$") == "x+1"
    assert strip_math_delimiters("$$x+1$$") == "x+1"


def test_extract_inline_and_display():
    md = r"Решите $x^2-9=0$ и $$\dfrac{a}{b}=c$$"
    out = extract_formulas(md)
    assert r"\frac{a}{b}=c" in out
    assert "x^2-9=0" in out


def test_extract_raw_keeps_original_spelling():
    # сырое извлечение не канонизует — на этом строится компиляция в KaTeX (С2)
    assert extract_formulas_raw(r"$\dfrac{a}{b}$") == [r"\dfrac{a}{b}"]


def test_extract_empty_when_no_math():
    assert extract_formulas("просто текст без формул") == []
