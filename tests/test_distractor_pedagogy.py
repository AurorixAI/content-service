"""Tests for distractor pedagogy apply logic (no LLM)."""
from src.pipeline.distractor_pedagogy import apply_pedagogy_review, looks_generic_error_logic
from src.schemas.smart_verify import PedagogyItemReview, PedagogyReviewResponse


def test_apply_rewrite_updates_both_fields():
    meta = [
        {"value": "5", "error_logic": "ошибка", "explanation": "ошибка"},
        {"value": "3", "error_logic": "типичная ошибка", "explanation": "типичная ошибка"},
    ]
    review = PedagogyReviewResponse(
        overall="pass",
        items=[
            PedagogyItemReview(index=0, status="ok"),
            PedagogyItemReview(
                index=1,
                status="rewrite",
                error_logic="вычел единицу вместо прибавления к промежуточному результату",
            ),
        ],
    )
    updated, outcome = apply_pedagogy_review(meta, review)
    assert outcome == "pass"
    assert updated[1]["error_logic"] == updated[1]["explanation"]
    assert "вычел единицу" in updated[1]["error_logic"]


def test_reject_value_needs_regen():
    meta = [
        {"value": "5", "error_logic": "достаточно длинное описание ошибки ученика"},
        {"value": "3", "error_logic": "ещё одно нормальное описание школьной ошибки"},
    ]
    review = PedagogyReviewResponse(
        overall="needs_regen",
        items=[
            PedagogyItemReview(index=0, status="ok"),
            PedagogyItemReview(index=1, status="reject_value", issue="value solves task"),
        ],
    )
    _, outcome = apply_pedagogy_review(meta, review)
    assert outcome == "needs_regen"


def test_looks_generic():
    assert looks_generic_error_logic("типичная ошибка")
    assert not looks_generic_error_logic(
        "перепутал знак при переносе слагаемого через знак равенства"
    )
