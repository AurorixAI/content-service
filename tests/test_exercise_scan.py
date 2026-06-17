"""Tests for exercise range scan heuristics."""
from src.pipeline.exercise_ranges.scan import (
    collect_exercise_numbers,
    resolve_paragraph_range,
)


def test_global_continuous():
    text = """
    ## Упражнения
    **640.** task one
    **652.** task last
    """
    r = resolve_paragraph_range(text, prev_hi=639)
    assert r is not None
    assert r.lo == 640 and r.hi == 652
    assert r.method.startswith("global")


def test_local_mapped_after_prev_hi():
    text = """
    ## Упражнения для работы в классе
    1. Первая задача
    2. Вторая
    25. Последняя
    """
    r = resolve_paragraph_range(text, prev_hi=699)
    assert r is not None
    assert r.lo == 700 and r.hi == 724
    assert r.count == 25
    assert "local" in r.method


def test_count_only_fallback():
    text = """
    Упражнения
    1. a
    3. b
    7. c
    """
    r = resolve_paragraph_range(text, prev_hi=100)
    assert r is not None
    assert r.lo == 101
    assert r.count == 3


def test_skips_theory_headers():
    text = """
    #### 1. Определение дроби
    Упражнения
    1. Вычислите
    2. Сравните
    """
    nums = collect_exercise_numbers(text)
    assert 1 in nums and 2 in nums
    assert nums.count(1) == 1  # not duplicated from theory
