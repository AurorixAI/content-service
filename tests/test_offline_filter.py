"""Tests for online/offline task filter heuristics."""
from src.pipeline.models import ExtractedTask
from src.pipeline.orchestrator import (
    _is_extraction_miss_placeholder,
    _is_offline_task,
    _recover_false_offline,
)


def _task(**kw) -> ExtractedTask:
    defaults = dict(
        temp_id="t1",
        exercise_number="1651",
        paragraph_number="68",
        question_text="Найдите среднее арифметическое ряда: 2, 4, 6, 8.",
        answer_raw="5",
        is_online_solvable=True,
        skip_reason="",
    )
    defaults.update(kw)
    return ExtractedTask(**defaults)


def test_false_offline_recovered_when_question_is_real():
    t = _task(
        is_online_solvable=False,
        skip_reason="номер отсутствует в тексте параграфа",
    )
    assert not _is_extraction_miss_placeholder(t)
    _recover_false_offline(t)
    assert t.is_online_solvable
    assert t.skip_reason == ""
    offline, _ = _is_offline_task(t)
    assert not offline


def test_extraction_miss_placeholder_dropped():
    t = _task(
        is_online_solvable=False,
        skip_reason="Задачи с номерами 1675-1679 отсутствуют в тексте",
        question_text="",
    )
    assert _is_extraction_miss_placeholder(t)


def test_real_offline_still_filtered():
    t = _task(
        is_online_solvable=False,
        skip_reason="требует чертеж в тетради",
        question_text="Постройте треугольник в тетради.",
    )
    assert not _is_extraction_miss_placeholder(t)
    _recover_false_offline(t)
    offline, reason = _is_offline_task(t)
    assert offline
    assert "чертеж" in reason or reason == "требует чертеж в тетради"
