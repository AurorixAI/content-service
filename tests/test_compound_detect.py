"""Tests for compound batch detection."""
from src.pipeline.compound_detect import detect_compound, plan_split_items


def test_g8_dezhz_compound():
    q = "Найдите значение корня: $\\sqrt{10^8}$; д) $\\sqrt{(-5)^4}$; е) $\\sqrt{(-2)^8}$"
    a = "10000; д) 25; е) 16"
    r = plan_split_items("G8_TB_17_394.4", q, a)
    assert r.should_split
    assert r.pattern == "g8_dezhz"
    assert r.n_subitems == 3
    assert r.exam_unsafe


def test_nested_split_child_still_compound():
    """First-level split child that is still a batch (д)е)…) must be flagged."""
    q = "Сравните числа:\n2 1/7 и 2,142; д) 1,(375) и 1 3/8; е) -3,(16) и -3 4/25"
    a = "2 1/7 > 2,142; д) 1,(375) = 1 3/8; е) -3,(16) < -3 4/25"
    r = detect_compound(
        task_id="G8_TB_11_274.4",
        question_text=q,
        correct_answer=a,
        tags={"split_from": "G8_TB_11_274"},
    )
    assert r.should_split
    assert r.nested_compound
    assert r.exam_unsafe


def test_atomic_split_child_ok():
    r = detect_compound(
        task_id="G8_TB_2_22.4.1",
        question_text="Упростите выражение (x-3)^2",
        correct_answer="(x-3)^2",
        tags={"split_from": "G8_TB_2_22.4"},
    )
    assert r.is_split_child
    assert not r.should_split


def test_atomic_single_answer():
    r = plan_split_items("G8_TB_1_1", "2+2", "4")
    assert not r.should_split


def test_g8_dezhz_not_inside_russian_word():
    """«в кубе)» must not trigger g8_dezhz (false OCR label)."""
    q = "Вычислите:\nкорень 6-й степени из (36 в кубе)"
    r = plan_split_items("G8_ALG_8_106.1.1", q, "6")
    assert not r.should_split
    r2 = detect_compound(
        task_id="G8_ALG_8_106.1.1",
        question_text=q,
        correct_answer="6",
        tags={"split_from": "G8_ALG_8_106.1"},
    )
    assert r2.is_split_child
    assert not r2.should_split


def test_numeric_compound():
    q = "Вычислите:\n1) 5+3\n2) 7*2"
    a = "1) 8; 2) 14"
    r = plan_split_items("G8_TB_x", q, a)
    assert r.should_split
    assert r.pattern == "numeric_12"
    assert r.n_subitems == 2
