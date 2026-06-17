"""Tests for quality gate."""
from src.pipeline.models import ExtractedTask
from src.pipeline.quality import passes_quality_gate


def test_quality_gate_requires_answer_for_numeric():
    t = ExtractedTask(
        temp_id="t1",
        question_text="Сколько будет 2+2?",
        answer_raw="",
        answer_type="exact_number",
    )
    assert not passes_quality_gate(t)


def test_quality_gate_allows_text_without_answer():
    t = ExtractedTask(
        temp_id="t2",
        question_text="Объясните, почему сумма углов треугольника равна 180°.",
        answer_raw="",
        answer_type="text",
    )
    assert passes_quality_gate(t)


def test_quality_gate_short_question_fails():
    t = ExtractedTask(
        temp_id="t3",
        question_text="2+2?",
        answer_raw="4",
        answer_type="exact_number",
    )
    assert not passes_quality_gate(t)
