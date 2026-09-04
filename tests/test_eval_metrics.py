"""Тесты метрик качества оцифровки (Сессия 1).

Метрики чистые — БД не нужна.
"""
from __future__ import annotations

from src.eval.metrics import (
    answer_join_coverage,
    evaluate,
    formula_compile_rate,
    int_prefix,
    latex_ned,
    missing_numbers,
    numbering_gaps,
    task_recall,
)


def _t(para: str, num: str, latex: str = "", answer_source=None) -> dict:
    return {
        "id": f"G8_{para}_{num}",
        "paragraph": para,
        "number": num,
        "question_text": "",
        "question_latex": latex,
        "correct_answer": "",
        "answer_source": answer_source,
    }


# ── int_prefix ─────────────────────────────────────────────────────────────
def test_int_prefix():
    assert int_prefix("142") == 142
    assert int_prefix("142а") == 142
    assert int_prefix("1.5") == 1
    assert int_prefix("А") is None
    assert int_prefix(None) is None


# ── task_recall ────────────────────────────────────────────────────────────
def test_task_recall_full_and_partial():
    golden = [{"paragraph": "12", "number": "1"}, {"paragraph": "12", "number": "2"}]
    assert task_recall(golden, [_t("12", "1"), _t("12", "2")]) == 1.0
    assert task_recall(golden, [_t("12", "1")]) == 0.5
    assert task_recall(golden, []) == 0.0


def test_task_recall_none_without_golden():
    # нет golden → метрика неопределена, а не 0.0
    assert task_recall([], [_t("12", "1")]) is None


def test_task_recall_number_alone_is_not_enough():
    # тот же номер в другом параграфе не должен засчитываться
    golden = [{"paragraph": "12", "number": "142"}]
    assert task_recall(golden, [_t("13", "142")]) == 0.0


# ── numbering_gaps ─────────────────────────────────────────────────────────
def test_numbering_gaps_detects_real_gap():
    tasks = [_t("12", "70"), _t("12", "72")]  # нет 71
    assert numbering_gaps(tasks) == 1
    assert missing_numbers(tasks) == {"12": [71]}


def test_numbering_gaps_order_independent():
    # двухколоночная вёрстка даёт скрембл 1,4,2,5,3,6 — это не разрыв
    tasks = [_t("12", n) for n in ("1", "4", "2", "5", "3", "6")]
    assert numbering_gaps(tasks) == 0


def test_numbering_gaps_scoped_per_paragraph():
    # нумерация сбрасывается в каждом параграфе — не считать 1..142 разрывом
    tasks = [_t("12", "142"), _t("13", "1")]
    assert numbering_gaps(tasks) == 0


def test_numbering_gaps_ignores_non_numeric():
    assert numbering_gaps([_t("12", "A"), _t("12", "B")]) == 0


# ── latex_ned ──────────────────────────────────────────────────────────────
def test_latex_ned_exact_match_is_zero():
    golden = [{"paragraph": "1", "number": "1", "formulas": ["x^2-9=0"]}]
    tasks = [_t("1", "1", "$x^2-9=0$")]
    assert latex_ned(golden, tasks) == 0.0


def test_latex_ned_ignores_cosmetics():
    # \dfrac vs \frac и лишние пробелы не должны штрафоваться
    golden = [{"paragraph": "1", "number": "1", "formulas": [r"\frac{a}{b}"]}]
    tasks = [_t("1", "1", r"$\dfrac{a}{b}$")]
    assert latex_ned(golden, tasks) == 0.0


def test_latex_ned_missing_task_is_worst():
    golden = [{"paragraph": "1", "number": "1", "formulas": ["x^2-9=0"]}]
    assert latex_ned(golden, []) == 1.0


def test_latex_ned_none_when_golden_has_no_formulas():
    # словесные задачи в метрику формул не входят
    golden = [{"paragraph": "1", "number": "1", "question_md": "Сколько яблок?"}]
    assert latex_ned(golden, [_t("1", "1")]) is None


# ── formula_compile_rate ───────────────────────────────────────────────────
def test_compile_rate_none_when_katex_unavailable(monkeypatch):
    # нет Node/katex → «не измеряли», а не 0.0
    import src.eval.metrics as m

    monkeypatch.setattr(m, "default_compiler", lambda: None)
    assert formula_compile_rate([_t("1", "1", "$x+1$")]) is None


def test_compile_rate_uses_katex_by_default(monkeypatch):
    # С2: компилятор не передан → берётся KaTeX, а не отдаётся None
    import src.eval.metrics as m

    monkeypatch.setattr(m, "default_compiler", lambda: (lambda fs: [True] * len(fs)))
    assert formula_compile_rate([_t("1", "1", "$x+1$")]) == 1.0


def test_compile_rate_with_stub_compiler():
    tasks = [_t("1", "1", "$x+1$"), _t("1", "2", r"$ight)$")]
    assert formula_compile_rate(tasks, lambda fs: [True, False]) == 0.5


# ── answer_join_coverage ───────────────────────────────────────────────────
def test_answer_coverage_none_before_session3():
    # колонки answer_source ещё нет → None, чтобы не путать с измеренным нулём
    assert answer_join_coverage([_t("1", "1"), _t("1", "2")]) is None


def test_answer_coverage_counts_book_key_only():
    tasks = [
        _t("1", "1", answer_source="book_key"),
        _t("1", "2", answer_source="ai_solved"),
    ]
    assert answer_join_coverage(tasks) == 0.5


# ── evaluate ───────────────────────────────────────────────────────────────
def test_evaluate_shape():
    m = evaluate([_t("12", "1")], [{"paragraph": "12", "number": "1"}], "G8")
    assert m["label"] == "G8"
    assert m["n_tasks"] == 1
    assert m["task_recall"] == 1.0
    assert m["formula_compile_rate"] is None  # формул в задаче нет → мерить нечего
    assert m["answer_join_coverage"] is None  # С3
