"""Safety tests for the isolated answer_options display backfill."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("backfill_answer_options_latex", SCRIPTS / "backfill_answer_options_latex.py")
assert SPEC and SPEC.loader
backfill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backfill)


class _Connection:
    def __init__(self, raw_options):
        self.raw_options = raw_options
        self.writes = []

    def execute(self, statement, params=None):
        if "SELECT answer_options" in str(statement):
            return type("Result", (), {"fetchone": lambda _self: (self.raw_options,)})()
        self.writes.append((str(statement), params))


def test_save_result_writes_parallel_latex_without_rewriting_raw_options():
    raw = [{"text": "1/2", "is_correct": True}, {"text": "1/3", "is_correct": False}]
    result = {
        "task_id": "task-1",
        "raw_options": raw,
        "raw_fingerprint": backfill.options_fingerprint(raw),
        "latex_options": [r"$\dfrac{1}{2}$", r"$\dfrac{1}{3}$"],
        "failures": {},
    }
    conn = _Connection(raw)

    backfill.save_result(conn, result)

    sql, params = conn.writes[0]
    assert "answer_options_latex" in sql
    assert json.loads(params["latex_options"]) == result["latex_options"]
    assert "latex_status" in conn.writes[1][0]
    assert raw == [{"text": "1/2", "is_correct": True}, {"text": "1/3", "is_correct": False}]


def test_save_result_rejects_concurrent_raw_option_change():
    raw = [{"text": "1/2"}]
    result = {
        "task_id": "task-1",
        "raw_options": raw,
        "raw_fingerprint": backfill.options_fingerprint(raw),
        "latex_options": [r"$\dfrac{1}{2}$"],
        "failures": {},
    }
    conn = _Connection([{"text": "1/4"}])

    with pytest.raises(RuntimeError, match="changed concurrently"):
        backfill.save_result(conn, result)
    assert conn.writes == []


def test_failed_option_latex_is_queued_for_review_without_raw_mutation():
    raw = [{"text": "неоднозначный вариант"}]
    result = {
        "task_id": "task-1",
        "raw_options": raw,
        "raw_fingerprint": backfill.options_fingerprint(raw),
        "latex_options": [""],
        "failures": {"0": "format_parse_failed"},
    }
    conn = _Connection(raw)

    backfill.save_result(conn, result)

    assert len(conn.writes) == 3
    assert "latex_status" in conn.writes[1][0]
    assert "review_queue" in conn.writes[2][0]
    assert raw == [{"text": "неоднозначный вариант"}]
