from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "mark_task_content_quality.py"
SPEC = importlib.util.spec_from_file_location("mark_task_content_quality", SCRIPT)
assert SPEC and SPEC.loader
quality = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quality)


def test_parse_findings_requires_explicit_reason_and_rejects_conflicts():
    assert quality.parse_findings(["task-1::wrong answer"]) == {"task-1": "wrong answer"}
    with pytest.raises(ValueError):
        quality.parse_findings(["task-1"])
    with pytest.raises(ValueError):
        quality.parse_findings(["task-1::first", "task-1::second"])


def test_source_fingerprint_ignores_status_and_latex_metadata():
    base = dict(
        question_text="Q", correct_answer="A", distractor_meta=[{"value": "B"}],
        answer_options=["A", "B"], verification_status="pending",
        latex_status="verified", is_active=True, tags={},
    )
    changed_metadata = {**base, "verification_status": "rejected", "is_active": False,
                        "latex_status": "partial", "tags": {"content_quality": {"status": "x"}}}

    assert quality.source_fingerprint(SimpleNamespace(**base)) == quality.source_fingerprint(
        SimpleNamespace(**changed_metadata)
    )


def test_source_fingerprint_changes_for_any_canonical_source_edit():
    base = SimpleNamespace(
        question_text="Q", correct_answer="A", distractor_meta=[{"value": "B"}],
        answer_options=["A", "B"],
    )
    changed = SimpleNamespace(
        question_text="Q", correct_answer="C", distractor_meta=[{"value": "B"}],
        answer_options=["A", "B"],
    )

    assert quality.source_fingerprint(base) != quality.source_fingerprint(changed)


def test_existing_invalid_preview_preserves_source_and_latex_metadata():
    row = SimpleNamespace(
        id="AUDITED_INVALID",
        question_text="Q",
        correct_answer="A",
        distractor_meta=[{"value": "B"}],
        answer_options=["A", "B"],
        verification_status="verified",
        latex_status="verified",
        is_active=False,
        tags={
            "content_quality": {
                "status": "mathematically_invalid",
                "reason": "professionally audited contradiction",
            }
        },
    )

    preview = quality._preview_row(
        row,
        reason=row.tags["content_quality"]["reason"],
    )

    assert preview["to_verification_status"] == "rejected"
    assert preview["latex_status_unchanged"] == "verified"
    assert preview["reason"] == "professionally audited contradiction"
    assert preview["source_fingerprint"] == quality.source_fingerprint(row)
