#!/usr/bin/env python3
"""Build the complete, read-only display-quality work queue.

The question-only audit answers whether ``question_latex`` can become the
sole UI projection.  This companion runner audits every user-visible display
field of a task: question, correct answer, answer options, distractor values
and distractor explanations.  It never invokes an LLM and never writes to the
database.  One persistent KaTeX process makes the full task-bank audit fast
enough to use as a repeatable release gate.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from collections import Counter
try:  # Python 3.11+
    from datetime import UTC, datetime
except ImportError:  # pragma: no cover - local audit compatibility on Python 3.9/3.10
    from datetime import datetime, timezone

    UTC = timezone.utc
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

from audit_question_latex_queue import KaTeXWorker  # noqa: E402
from backfill_latex_deepseek import (  # noqa: E402
    _canonical_dmeta,
    _canonical_options,
    validate_display_contract,
    validate_professional_latex,
)


def _json_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _display_fingerprint(
    question_text: object,
    correct_answer: object,
    distractor_meta: object,
    answer_options: object,
) -> str:
    """Fingerprint canonical source only; display values are intentionally excluded."""
    canonical = {
        "question_text": question_text or "",
        "correct_answer": correct_answer or "",
        "distractor_meta": _canonical_dmeta(distractor_meta if distractor_meta is not None else []),
        "answer_options": _canonical_options(answer_options or []),
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _field_rows(
    question_text: object,
    question_latex: object,
    correct_answer: object,
    correct_answer_latex: object,
    distractor_meta: object,
    answer_options: object,
    answer_options_latex: object,
) -> Iterator[tuple[str, str, str]]:
    yield "question", str(question_text or "").strip(), str(question_latex or "").strip()
    yield "answer", str(correct_answer or "").strip(), str(correct_answer_latex or "").strip()

    for index, item in enumerate(_json_list(distractor_meta)):
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or item.get("text") or item.get("content") or "").strip()
        value_latex = str(
            item.get("value_latex") or item.get("text_latex") or item.get("content_latex") or ""
        ).strip()
        yield f"dmeta[{index}].value", value, value_latex
        raw_key, display_key = (
            ("error_logic", "error_logic_latex")
            if str(item.get("error_logic") or "").strip()
            else ("explanation", "explanation_latex")
        )
        yield f"dmeta[{index}].description", str(item.get(raw_key) or "").strip(), str(item.get(display_key) or "").strip()

    raw_options = _json_list(answer_options)
    display_options = _json_list(answer_options_latex)
    for index, option in enumerate(raw_options):
        raw = (
            str(option.get("value") or option.get("text") or option.get("content") or "").strip()
            if isinstance(option, dict) else str(option or "").strip()
        )
        display = str(display_options[index] or "").strip() if index < len(display_options) else ""
        yield f"option[{index}]", raw, display


def _risk(field: str, reasons: list[str]) -> str:
    joined = " ".join(reasons)
    if field == "question" and ("invalid.katex" in joined or "semantic." in joined):
        return "critical"
    if "invalid.katex" in joined or "semantic." in joined:
        return "high"
    if "missing_display_value" in joined or "contract." in joined:
        return "medium"
    return "low"


def _derived_status(issue_count: int, required_count: int) -> str:
    if issue_count == 0:
        return "verified"
    return "failed" if required_count and issue_count == required_count else "partial"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only full display-quality audit")
    parser.add_argument("--output", required=True, help="Path for reproducible JSON queue")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL") or "postgresql://algo:algo_password@127.0.0.1:5434/algo_content"
    query = text("""
        SELECT id, question_text, question_latex, correct_answer,
               correct_answer_latex, distractor_meta, answer_options,
               answer_options_latex, latex_status
        FROM tasks_master
        WHERE is_active = TRUE
          AND verification_status = 'verified'
        ORDER BY id
    """)

    reason_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    task_kind_counts: Counter[str] = Counter()
    queue: list[dict[str, Any]] = []
    checked = 0

    engine = create_engine(db_url)
    with engine.connect() as conn, KaTeXWorker() as katex:
        for row in conn.execute(query):
            checked += 1
            (
                task_id, question_text, question_latex, correct_answer,
                correct_answer_latex, distractor_meta, answer_options,
                answer_options_latex, stored_status,
            ) = row
            issues: list[dict[str, Any]] = []
            required = 0
            for label, raw, display in _field_rows(
                question_text, question_latex, correct_answer, correct_answer_latex,
                distractor_meta, answer_options, answer_options_latex,
            ):
                if not raw:
                    continue
                required += 1
                reasons: list[str] = []
                if not display:
                    reasons.append("missing_display_value")
                else:
                    katex_ok, katex_error = katex.validate(display)
                    if not katex_ok:
                        reasons.append(f"invalid.katex.{katex_error or 'unknown'}")
                    contract_ok, contract_reason = validate_display_contract(label, raw, display)
                    if not contract_ok:
                        reasons.append(f"contract.{contract_reason}")
                    professional_ok, professional_reason = validate_professional_latex(display)
                    if not professional_ok:
                        reasons.append(f"professional.{professional_reason}")
                if not reasons:
                    continue
                unique_reasons = list(dict.fromkeys(reasons))
                issues.append({
                    "field": label,
                    "risk": _risk(label, unique_reasons),
                    "reasons": unique_reasons,
                })
                field_counts[label.split("[", 1)[0].split(".", 1)[0]] += 1
                reason_counts.update(unique_reasons)

            derived_status = _derived_status(len(issues), required)
            status_mismatch = str(stored_status or "null") != derived_status
            if not issues and not status_mismatch:
                continue
            task_kind = "status_only" if not issues else "display_repair"
            task_kind_counts[task_kind] += 1
            queue.append({
                "task_id": str(task_id),
                "risk": min((issue["risk"] for issue in issues), key=("critical", "high", "medium", "low").index, default="low"),
                "kind": task_kind,
                "stored_latex_status": str(stored_status or "null"),
                "derived_latex_status": derived_status,
                "canonical_fingerprint_sha256": _display_fingerprint(
                    question_text, correct_answer, distractor_meta, answer_options,
                ),
                "issues": issues,
            })

    payload = {
        "mode": "read_only",
        "generated_at": datetime.now(UTC).isoformat(),
        "selection": {"is_active": True, "verification_status": "verified"},
        "tasks_checked": checked,
        "quality_queue_count": len(queue),
        "task_kind_counts": dict(sorted(task_kind_counts.items())),
        "field_issue_counts": dict(sorted(field_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "records": queue,
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "tasks_checked": checked,
        "quality_queue_count": len(queue),
        "task_kind_counts": payload["task_kind_counts"],
        "field_issue_counts": payload["field_issue_counts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
