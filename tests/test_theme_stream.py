"""Tests for theme-stream detector and matcher."""
from __future__ import annotations

from src.pipeline.theme_stream.detector import find_markers
from src.pipeline.theme_stream.matcher import TocMatcher


def test_finds_theme_range_header():
    text = "\n**3–5 Признаки делимости чисел на 10, на 5 и на 2**\n\nSome theory."
    markers = find_markers(text)
    assert any(m.number == "3-5" and m.kind == "theme" for m in markers)


def test_finds_repetition_header():
    text = "### 2. Обыкновенные дроби\n\n**8.** Вычислите"
    markers = find_markers(text)
    assert any(m.kind == "repetition" and m.number == "2" for m in markers)


def test_finds_self_test():
    text = "Тест I\nПроверьте себя!\n\n**100.** Решите"
    markers = find_markers(text)
    assert any(m.kind == "self_test" for m in markers)


def test_matcher_theme():
    leaves = [
        {"id": 1, "number": "3–5", "title": "Признаки делимости на 10, 5 и 2"},
    ]
    m = TocMatcher(leaves)
    from src.pipeline.theme_stream.detector import ThemeMarker
    mk = ThemeMarker("theme", "3-5", "Признаки делимости", "3-5 Признаки", 0)
    entry, conf = m.match(mk)
    assert entry is not None
    assert conf >= 0.75
