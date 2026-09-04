"""Приём выгрузки прототипа в контур content-service."""

import json

import pytest

from src.pipeline import provenance as prov
from src.pipeline.prototype_ingest import discover_books, load_book, to_task


def rec(**kw):
    base = {
        "task_id": "BK_p5_1",
        "page": 5,
        "number": "1",
        "kind": "exercise",
        "statement_md": "Найдите значение $x$",
        "subtasks": [],
        "answer": None,
        "confidence": {"ocr": 1.0, "structure": 0.9},
        "needs_review": False,
        "flags": [],
    }
    base.update(kw)
    return base


class TestToTask:
    def test_basic_fields(self):
        t = to_task(rec(), "BK")
        assert t.temp_id == "BK_p5_1"
        assert t.exercise_number == "1"
        assert t.page == 5

    def test_confidence_carried_over(self):
        """У прототипа уже есть словарь И1 — сигнал переносится, не теряется."""
        t = to_task(rec(), "BK")
        assert t.confidence == {"ocr": 1.0, "structure": 0.9}

    def test_no_answer_means_absent_source(self):
        assert to_task(rec(), "BK").answer_source == prov.ABSENT

    def test_book_answer_marked_as_book_key(self):
        t = to_task(rec(answer={"md": "42", "source_page": 93}), "BK")
        assert t.answer_raw == "42"
        assert t.answer_source == prov.BOOK_KEY
        assert t.answer_source_page == 93

    def test_latin_labels_become_choices(self):
        t = to_task(rec(subtasks=[
            {"label": "A)", "md": "3"}, {"label": "B)", "md": "5"},
            {"label": "C)", "md": "7"}, {"label": "D)", "md": "1"},
        ]), "BK")
        assert t.answer_type == "multiple_choice"
        assert t.answer_options == ["3", "5", "7", "1"]

    def test_cyrillic_labels_are_subparts_not_choices(self):
        """«а) б) в)» — подпункты одной задачи, а не варианты выбора."""
        t = to_task(rec(subtasks=[
            {"label": "а)", "md": "2+2"}, {"label": "б)", "md": "3+3"},
        ]), "BK")
        assert t.answer_type == "exact_number"
        assert t.answer_options is None

    def test_single_subtask_is_not_mcq(self):
        t = to_task(rec(subtasks=[{"label": "A)", "md": "3"}]), "BK")
        assert t.answer_type == "exact_number"

    def test_paragraph_left_empty_on_purpose(self):
        """Прототип резал книгу постранично — параграфа у него нет."""
        assert to_task(rec(), "BK").paragraph_number == ""

    def test_latex_not_duplicated_into_two_fields(self):
        """Иначе гейты посчитали бы каждую формулу дважды."""
        t = to_task(rec(), "BK")
        assert t.question_latex == ""
        assert "$x$" in t.question_text

    def test_needs_review_becomes_a_flag(self):
        t = to_task(rec(needs_review=True, flags=["низкий ocr"]), "BK")
        assert "низкий ocr" in t.review_flags
        assert any("needs_review" in f for f in t.review_flags)

    def test_tags_keep_book_and_kind(self):
        t = to_task(rec(kind="exercise"), "BK")
        assert t.tags["book_id"] == "BK"
        assert t.tags["kind"] == "exercise"


class TestLoadBook:
    def _write(self, d, tasks, answers=None):
        (d / "tasks.json").write_text(
            json.dumps({"book_id": d.name, "tasks": tasks}, ensure_ascii=False),
            encoding="utf-8",
        )
        if answers is not None:
            (d / "answers.json").write_text(
                json.dumps({"answers": answers}, ensure_ascii=False), encoding="utf-8"
            )

    def test_loads_tasks_and_answers(self, tmp_path):
        d = tmp_path / "bk"; d.mkdir()
        self._write(d, [rec()], [{"number": "1", "answer_md": "42", "source_page": 93}])
        tasks, answers = load_book(d)
        assert len(tasks) == 1 and len(answers) == 1

    def test_missing_answers_file_is_not_an_error(self, tmp_path):
        d = tmp_path / "bk"; d.mkdir()
        self._write(d, [rec()])
        tasks, answers = load_book(d)
        assert len(tasks) == 1 and answers == []

    def test_non_exercises_dropped_by_default(self, tmp_path):
        d = tmp_path / "bk"; d.mkdir()
        self._write(d, [rec(), rec(kind="definition"), rec(kind="theorem")])
        tasks, _ = load_book(d)
        assert len(tasks) == 1

    def test_non_exercises_kept_when_asked(self, tmp_path):
        d = tmp_path / "bk"; d.mkdir()
        self._write(d, [rec(), rec(kind="definition")])
        tasks, _ = load_book(d, exercises_only=False)
        assert len(tasks) == 2

    def test_missing_tasks_file(self, tmp_path):
        d = tmp_path / "empty"; d.mkdir()
        assert load_book(d) == ([], [])

    def test_discover_skips_dirs_without_tasks(self, tmp_path):
        good = tmp_path / "good"; good.mkdir()
        self._write(good, [rec()])
        (tmp_path / "bad").mkdir()
        assert [p.name for p in discover_books(tmp_path)] == ["good"]

    def test_discover_on_missing_root(self, tmp_path):
        assert discover_books(tmp_path / "nope") == []


class TestSubtaskStatementRecovery:
    """B1: текст подпунктов не должен теряться при приёме."""

    def test_statement_built_from_subtasks_when_empty(self):
        rec = {
            "number": "1",
            "statement_md": "",
            "subtasks": [
                {"label": "а)", "md": "Ученик обточил 120 деталей."},
                {"label": "б)", "md": "Токарь — на 36 больше."},
            ],
        }
        t = to_task(rec, "book")
        assert "Ученик обточил 120 деталей." in t.question_text
        assert "Токарь — на 36 больше." in t.question_text

    def test_own_statement_wins_over_subtasks(self):
        rec = {
            "number": "1",
            "statement_md": "Решите уравнение.",
            "subtasks": [{"label": "а)", "md": "x = 1"}],
        }
        assert to_task(rec, "book").question_text == "Решите уравнение."

    def test_mcq_options_not_folded_into_statement(self):
        rec = {
            "number": "1",
            "statement_md": "",
            "subtasks": [
                {"label": "A", "md": "2"}, {"label": "B", "md": "3"},
                {"label": "C", "md": "4"}, {"label": "D", "md": "5"},
            ],
        }
        t = to_task(rec, "book")
        assert t.answer_type == "multiple_choice"
        assert t.question_text == ""
