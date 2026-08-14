"""Regression tests for Smart Verify operational queue safety."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


_SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_SCRIPT = _SCRIPTS / "run_smart_verify.py"
_SPEC = importlib.util.spec_from_file_location("run_smart_verify", _SCRIPT)
assert _SPEC and _SPEC.loader
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


class _ScalarResult:
    def __init__(self, value):
        self.value = value
        self.rowcount = 1 if value is not None else 0

    def scalar_one_or_none(self):
        return self.value


class _ClaimConnection:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _ScalarResult(self.value)


class _ClaimTransaction:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *_args):
        return False


class _ClaimEngine:
    def __init__(self, value):
        self.conn = _ClaimConnection(value)

    def begin(self):
        return _ClaimTransaction(self.conn)


def test_claim_task_is_atomic_and_carries_a_worker_lease():
    engine = _ClaimEngine("T1")

    assert runner.claim_task(engine, "T1", "worker-1", claim_ttl_seconds=1800)

    sql, params = engine.conn.calls[0]
    assert "UPDATE tasks_master AS tm" in sql
    assert "smart_verify_claim_id" in sql
    assert "smart_verify_claimed_at" in sql
    assert "RETURNING tm.id" in sql
    assert params == {
        "task_id": "T1",
        "claim_id": "worker-1",
        "claim_ttl_seconds": 1800,
    }


def test_claim_task_refuses_a_task_already_owned_by_another_worker():
    engine = _ClaimEngine(None)

    assert not runner.claim_task(engine, "T1", "worker-2")


def test_release_task_claim_only_releases_the_owning_worker_lease():
    engine = _ClaimEngine("T1")

    assert runner.release_task_claim(engine, "T1", "worker-1")

    sql, params = engine.conn.calls[0]
    assert "smart_verify_claim_id" in sql
    assert "smart_verify_claimed_at" in sql
    assert params == {"task_id": "T1", "claim_id": "worker-1"}


def test_parse_levels_accepts_a_single_grade():
    assert runner._parse_levels(SimpleNamespace(grades="11", class_level=None)) == (11,)
    assert runner._parse_levels(SimpleNamespace(grades="9-11", class_level=None)) == (9, 10, 11)


def test_distractor_queue_uses_full_gate_instead_of_sql_length_or_flags():
    class _FetchResult:
        def fetchall(self):
            return []

    class _FetchConnection:
        def __init__(self):
            self.sql = ""

        def execute(self, statement, _params):
            self.sql = str(statement)
            return _FetchResult()

    class _FetchContext:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, *_args):
            return False

    class _FetchEngine:
        def __init__(self):
            self.conn = _FetchConnection()

        def connect(self):
            return _FetchContext(self.conn)

    engine = _FetchEngine()
    runner.fetch_tasks(
        engine,
        levels=(10,),
        limit=10,
        task_id=None,
        reprocess=False,
        gaps_only=True,
    )

    sql = engine.conn.sql
    assert "verification_status = 'pending'" in sql
    assert "verified_match" in sql
    assert "verified_corrected" in sql
    assert "jsonb_array_length" not in sql
    assert "choices_complete" not in sql


def test_final_certification_never_trusts_stale_choices_complete(monkeypatch):
    monkeypatch.setattr(runner, "distractors_valid", lambda *_args, **_kwargs: False)

    tags, status, valid = runner.certify_final_verification(
        {
            "smart_verify_status": "verified_match",
            "choices_complete": True,
        },
        [{"value": "wrong", "error_logic": "some explanation"}],
        question="2 + 2 = ?",
        correct_answer="4",
        answer_type="exact_number",
    )

    assert status == "pending"
    assert valid is False
    assert tags["choices_complete"] is False


def test_final_certification_closes_stale_regen_flags_without_llm(monkeypatch):
    monkeypatch.setattr(runner, "distractors_valid", lambda *_args, **_kwargs: True)

    tags, status, valid = runner.certify_final_verification(
        {
            "smart_verify_status": "verified_corrected",
            "choices_complete": False,
            "distractor_regen_pending": True,
            "distractor_regen_exhausted": True,
        },
        [{"value": "3", "error_logic": "student added incorrectly"}],
        question="2 + 2 = ?",
        correct_answer="4",
        answer_type="exact_number",
    )

    assert status == "verified"
    assert valid is True
    assert tags["choices_complete"] is True
    assert "distractor_regen_pending" not in tags
    assert "distractor_regen_exhausted" not in tags


def test_response_queue_targets_legacy_semantic_answers_without_retry_filter():
    class _FetchResult:
        def fetchall(self):
            return []

    class _FetchConnection:
        def __init__(self):
            self.sql = ""

        def execute(self, statement, _params):
            self.sql = str(statement)
            return _FetchResult()

    class _FetchContext:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, *_args):
            return False

    class _FetchEngine:
        def __init__(self):
            self.conn = _FetchConnection()

        def connect(self):
            return _FetchContext(self.conn)

    engine = _FetchEngine()
    runner.fetch_tasks(
        engine,
        levels=(5,),
        limit=25,
        task_id=None,
        reprocess=False,
        queue_kind="response",
    )

    assert "failed_at_sympy" in engine.conn.sql
    assert "smart_verify_retry_exhausted" not in engine.conn.sql
    assert "mathematically_invalid" in engine.conn.sql


def test_response_queue_excludes_rows_already_processed_by_response_route():
    class _FetchResult:
        def fetchall(self):
            return []

    class _FetchConnection:
        def __init__(self):
            self.sql = ""
            self.params = None

        def execute(self, statement, params):
            self.sql = str(statement)
            self.params = params
            return _FetchResult()

    class _FetchContext:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, *_args):
            return False

    class _FetchEngine:
        def __init__(self):
            self.conn = _FetchConnection()

        def connect(self):
            return _FetchContext(self.conn)

    engine = _FetchEngine()
    runner.fetch_tasks(
        engine,
        levels=(5,),
        limit=25,
        task_id=None,
        reprocess=False,
        queue_kind="response",
    )

    assert "smart_verify_effective_answer_type" in engine.conn.sql
    assert "!= 'text'" in engine.conn.sql


def test_retry_queue_excludes_final_human_review_rows():
    class _FetchResult:
        def fetchall(self):
            return []

    class _FetchConnection:
        def __init__(self):
            self.sql = ""

        def execute(self, statement, _params):
            self.sql = str(statement)
            return _FetchResult()

    class _FetchContext:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, *_args):
            return False

    class _FetchEngine:
        def __init__(self):
            self.conn = _FetchConnection()

        def connect(self):
            return _FetchContext(self.conn)

    engine = _FetchEngine()
    runner.fetch_tasks(
        engine,
        levels=(7,),
        limit=25,
        task_id=None,
        reprocess=False,
        queue_kind="retry",
    )

    assert "smart_verify_retry_exhausted" in engine.conn.sql
    assert "human_reprocess_exhausted" in engine.conn.sql


def test_human_reprocess_queue_excludes_already_terminal_rows():
    class _FetchResult:
        def fetchall(self):
            return []

    class _FetchConnection:
        def __init__(self):
            self.sql = ""

        def execute(self, statement, _params):
            self.sql = str(statement)
            return _FetchResult()

    class _FetchContext:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, *_args):
            return False

    class _FetchEngine:
        def __init__(self):
            self.conn = _FetchConnection()

        def connect(self):
            return _FetchContext(self.conn)

    engine = _FetchEngine()
    runner.fetch_tasks(
        engine,
        levels=(7,),
        limit=25,
        task_id=None,
        reprocess=True,
        reprocess_run_id="human-terminal-test",
        queue_kind="human",
    )

    assert "smart_verify_retry_exhausted" in engine.conn.sql
    assert "human_reprocess_exhausted" in engine.conn.sql


def test_boolean_queue_isolated_to_old_boolean_evidence():
    class _FetchResult:
        def fetchall(self):
            return []

    class _FetchConnection:
        def __init__(self):
            self.sql = ""

        def execute(self, statement, _params):
            self.sql = str(statement)
            return _FetchResult()

    class _FetchContext:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, *_args):
            return False

    class _FetchEngine:
        def __init__(self):
            self.conn = _FetchConnection()

        def connect(self):
            return _FetchContext(self.conn)

    engine = _FetchEngine()
    runner.fetch_tasks(
        engine,
        levels=(7,),
        limit=25,
        task_id=None,
        reprocess=False,
        queue_kind="boolean",
    )

    assert "invalid_boolean_result" in engine.conn.sql
    assert "failed_at_sympy" in engine.conn.sql
    assert "smart_verify_effective_answer_type" in engine.conn.sql


def test_response_queue_forces_the_safe_text_route(monkeypatch):
    captured = {}

    monkeypatch.setattr(runner, "claim_task", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runner, "release_task_claim", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        runner,
        "run_text_verify_pipeline",
        lambda **kwargs: captured.update(kwargs) or {
            "status": "review",
            "correct_answer": kwargs["correct_answer"],
            "distractor_meta": kwargs["distractor_meta"],
            "tags": {"smart_verify_status": "needs_human_review"},
            "action": "needs_human_review_source_preserved",
            "verification_status": "pending",
        },
    )
    monkeypatch.setattr(
        runner,
        "fetch_tasks",
        lambda *_args, **_kwargs: [
            ("LEGACY", "Сравните числа.", "Верно, первое больше", "exact_number", [], {})
        ],
    )
    monkeypatch.setattr(runner, "persist_result", lambda *_args, **_kwargs: True)

    args = SimpleNamespace(
        class_level=None, grades="5", task_id=None, queue="response",
        gaps_only=False, retry_failed=False, only_human_review=False,
        limit=1, reprocess=False, reprocess_run_id=None, skip_text=False,
        answer_type=None, id_prefix=None, only_fix_g7_failed=False,
        only_fix_g7_reprocess_failed=False, only_fix_g6_reverify=False,
        skip_coordinate=False, all_gap_types=False, source_run_id=None,
        run_id="response-test", claim_id="response-test",
        claim_ttl_seconds=60, dry_run=False, answer_authority="textbook",
        sleep=0, workers=1,
    )

    stats = runner.run_batch(object(), args)

    assert captured["answer_type"] == "text"
    assert captured["preserve_source_on_mismatch"] is True
    assert stats["needs_human_review"] == 1


def test_replay_queue_does_not_intersect_response_recovery_rows():
    class _FetchResult:
        def fetchall(self):
            return []

    class _FetchConnection:
        def __init__(self):
            self.sql = ""

        def execute(self, statement, _params):
            self.sql = str(statement)
            return _FetchResult()

    class _FetchContext:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, *_args):
            return False

    class _FetchEngine:
        def __init__(self):
            self.conn = _FetchConnection()

        def connect(self):
            return _FetchContext(self.conn)

    engine = _FetchEngine()
    runner.fetch_tasks(
        engine,
        levels=(9,),
        limit=25,
        task_id=None,
        reprocess=False,
        queue_kind="replay",
    )

    assert "answer_gemini_candidate" in engine.conn.sql
    assert "smart_verify_effective_answer_type" in engine.conn.sql
    assert "smart_verify_replay_run_id" in engine.conn.sql


def test_replay_queue_excludes_rows_processed_in_the_same_run():
    class _FetchResult:
        def fetchall(self):
            return []

    class _FetchConnection:
        def __init__(self):
            self.sql = ""
            self.params = None

        def execute(self, statement, params):
            self.sql = str(statement)
            self.params = params
            return _FetchResult()

    class _FetchContext:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, *_args):
            return False

    class _FetchEngine:
        def __init__(self):
            self.conn = _FetchConnection()

        def connect(self):
            return _FetchContext(self.conn)

    engine = _FetchEngine()
    runner.fetch_tasks(
        engine,
        levels=(9,),
        limit=25,
        task_id=None,
        reprocess=False,
        queue_kind="replay",
        replay_run_id="replay-run-1",
    )

    assert "!= :replay_run_id" in engine.conn.sql
    assert "smart_verify_run_id" in engine.conn.sql
    assert engine.conn.params["replay_run_id"] == "replay-run-1"
