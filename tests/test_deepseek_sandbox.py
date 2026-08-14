"""Hard timeout behaviour for locally generated SymPy code."""
from __future__ import annotations

import time

import pytest

from src.pipeline import deepseek_client


def test_sandbox_returns_result_from_child_process():
    namespace = deepseek_client._run_code_in_sandbox(
        'result = {"sympy_compatible_string": "2+2", "absolute_correct_answer": "4"}'
    )
    assert namespace["result"]["absolute_correct_answer"] == "4"


def test_sandbox_kills_non_terminating_code(monkeypatch):
    monkeypatch.setattr(deepseek_client, "_LOCAL_EXEC_TIMEOUT_S", 0.2)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        deepseek_client._run_code_in_sandbox("while True:\n    pass")
    assert time.monotonic() - started < 3
