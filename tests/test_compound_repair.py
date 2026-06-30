"""Tests for compound repair classification."""
from src.pipeline.compound_repair import (
    CompoundIssue,
    classify_compound_issue,
    trim_orphan_question_tail,
)


def test_trim_orphan_dezhz():
    q = "Упростите: $3\\sqrt{8}$; д) $\\sqrt{98}$"
    trimmed, ok = trim_orphan_question_tail(q)
    assert ok
    assert "д)" not in trimmed
    assert "3" in trimmed


def test_classify_orphan_tail():
    r = classify_compound_issue(
        task_id="G8_TB_18_414.3",
        question_text="Упростите: expr1; д) expr2",
        correct_answer="2.0*sqrt(2)",
        answer_type="expression",
        tags={},
        split_item_count=2,
        split_second_answer_empty=True,
    )
    assert r.issue == CompoundIssue.ORPHAN_TAIL


def test_classify_stale_tag():
    r = classify_compound_issue(
        task_id="G8_TB_2_11.1",
        question_text="Укажите ОДЗ: x^2",
        correct_answer="любое число",
        answer_type="set",
        tags={"needs_compound_split": True, "split_from": "G8_TB_2_11"},
        split_item_count=0,
    )
    assert r.issue == CompoundIssue.STALE_TAG


def test_classify_broken_batch():
    r = classify_compound_issue(
        task_id="G8_TB_1_10",
        question_text="При каких значениях переменной имеет смысл выражение:",
        correct_answer="а) x ≠ 2; б) любые b; в) y ≠ 0",
        answer_type="set",
        tags={},
        split_item_count=0,
    )
    assert r.issue == CompoundIssue.BROKEN_BATCH
