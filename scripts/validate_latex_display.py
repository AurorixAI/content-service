#!/usr/bin/env python3
"""Read-only audit for the LaTeX display contract.

This tool never calls an LLM and never executes INSERT/UPDATE/DELETE.  It is
the required gate before any LaTeX backfill: it reports which display fields
are absent while keeping canonical educational content out of the write path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any, Iterable

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS_DIR)
load_dotenv(os.path.join(ROOT, ".env"))

from backfill_latex_deepseek import (  # noqa: E402
    semantic_preservation_check,
    validate_display_contract,
    validate_professional_latex,
    validate_with_katex,
)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _first_text(item: Any, keys: Iterable[str]) -> str:
    if not isinstance(item, dict):
        return ""
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _has_semantic_drift(source: str, display: str) -> bool:
    """Return true only when formatting has changed source meaning/coverage."""
    # Stored display is allowed to repair malformed legacy delimiter
    # boundaries, exactly like an accepted REPLACE/KEEP in the backfill. The
    # invariant token check still rejects changed words, numbers and operators.
    return not semantic_preservation_check(
        source, display, allow_legacy_markup_repair=True,
    )[0]


def validate_task(
    row: dict[str, Any], *, check_katex: bool = False, check_semantics: bool = False,
) -> list[str]:
    """Return stable issue codes for one task, without modifying its data."""
    issues: list[str] = []
    question_latex = str(row.get("question_latex") or "").strip()
    answer_latex = str(row.get("correct_answer_latex") or "").strip()
    if str(row.get("question_text") or "").strip() and not question_latex:
        issues.append("missing.question_latex")
    elif question_latex:
        if not validate_display_contract("question", str(row.get("question_text") or ""), question_latex)[0]:
            issues.append("contract.question_latex")
        if not validate_professional_latex(question_latex)[0]:
            issues.append("professional.question_latex")
        if check_katex and not validate_with_katex(question_latex)[0]:
            issues.append("invalid.question_latex")
        if check_semantics and _has_semantic_drift(str(row.get("question_text") or ""), question_latex):
            issues.append("semantic.question_latex")
    if str(row.get("correct_answer") or "").strip() and not answer_latex:
        issues.append("missing.correct_answer_latex")
    elif answer_latex:
        if not validate_display_contract("answer", str(row.get("correct_answer") or ""), answer_latex)[0]:
            issues.append("contract.correct_answer_latex")
        if not validate_professional_latex(answer_latex)[0]:
            issues.append("professional.correct_answer_latex")
        if check_katex and not validate_with_katex(answer_latex)[0]:
            issues.append("invalid.correct_answer_latex")
        if check_semantics and _has_semantic_drift(str(row.get("correct_answer") or ""), answer_latex):
            issues.append("semantic.correct_answer_latex")

    distractors = _as_list(row.get("distractor_meta"))
    for index, distractor in enumerate(distractors):
        canonical_value = _first_text(distractor, ("value", "text", "content"))
        has_value_latex = bool(_first_text(distractor, ("value_latex", "text_latex", "content_latex")))
        if canonical_value and not has_value_latex:
            issues.append(f"missing.distractor[{index}].value_latex")
        elif check_katex and has_value_latex:
            value_latex = _first_text(distractor, ("value_latex", "text_latex", "content_latex"))
            if not validate_with_katex(value_latex)[0]:
                issues.append(f"invalid.distractor[{index}].value_latex")
        if canonical_value and has_value_latex:
            value_latex = _first_text(distractor, ("value_latex", "text_latex", "content_latex"))
            if not validate_display_contract(f"dmeta[{index}].value", canonical_value, value_latex)[0]:
                issues.append(f"contract.distractor[{index}].value_latex")
            if not validate_professional_latex(value_latex)[0]:
                issues.append(f"professional.distractor[{index}].value_latex")
        if canonical_value and has_value_latex and check_semantics:
            value_latex = _first_text(distractor, ("value_latex", "text_latex", "content_latex"))
            if _has_semantic_drift(canonical_value, value_latex):
                issues.append(f"semantic.distractor[{index}].value_latex")

        # explanation is a legacy mirror of error_logic. The display contract
        # has one error-description slot: error_logic first, explanation only
        # where older content has no error_logic.
        description_key, description_latex_key = (
            ("error_logic", "error_logic_latex")
            if _first_text(distractor, ("error_logic",))
            else ("explanation", "explanation_latex")
        )
        if _first_text(distractor, (description_key,)) and not _first_text(distractor, (description_latex_key,)):
            issues.append(f"missing.distractor[{index}].description_latex")
        elif check_katex:
            description_latex = _first_text(distractor, (description_latex_key,))
            if description_latex and not validate_with_katex(description_latex)[0]:
                issues.append(f"invalid.distractor[{index}].description_latex")
        description = _first_text(distractor, (description_key,))
        description_latex = _first_text(distractor, (description_latex_key,))
        if description and description_latex and not validate_display_contract(
            f"dmeta[{index}].description", description, description_latex,
        )[0]:
            issues.append(f"contract.distractor[{index}].description_latex")
        if description and description_latex and not validate_professional_latex(description_latex)[0]:
            issues.append(f"professional.distractor[{index}].description_latex")
        if description and description_latex and check_semantics and _has_semantic_drift(description, description_latex):
            issues.append(f"semantic.distractor[{index}].description_latex")

    # Some legacy tasks use answer_options independently from distractor_meta.
    # Report them explicitly: this is a schema repair candidate, not a reason
    # to silently overwrite the option or invent its display value.
    answer_options_latex = _as_list(row.get("answer_options_latex"))
    for index, option in enumerate(_as_list(row.get("answer_options"))):
        canonical_value = _first_text(option, ("value", "text", "content")) if isinstance(option, dict) else str(option).strip()
        has_latex = (
            str(answer_options_latex[index]).strip()
            if index < len(answer_options_latex) and answer_options_latex[index] is not None
            else _first_text(option, ("value_latex", "text_latex", "content_latex", "latex")) if isinstance(option, dict) else ""
        )
        # The parallel array is deliberately independent from distractor_meta:
        # a renderer must not guess which distractor happens to match an option.
        if canonical_value and not has_latex:
            issues.append(f"missing.answer_options[{index}].latex")
        elif has_latex:
            if not validate_display_contract(f"option[{index}]", canonical_value, str(has_latex))[0]:
                issues.append(f"contract.answer_options[{index}].latex")
            if not validate_professional_latex(str(has_latex))[0]:
                issues.append(f"professional.answer_options[{index}].latex")
            if check_katex and not validate_with_katex(str(has_latex))[0]:
                issues.append(f"invalid.answer_options[{index}].latex")
            if check_semantics and _has_semantic_drift(canonical_value, str(has_latex)):
                issues.append(f"semantic.answer_options[{index}].latex")

    return issues


def expected_status(issues: list[str]) -> str:
    return "verified" if not issues else "partial"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only LaTeX display contract audit")
    parser.add_argument("--limit", type=int, default=0, help="Check only this many active tasks")
    parser.add_argument("--task-id", action="append", default=[], help="Check an exact task ID (repeatable)")
    parser.add_argument(
        "--latex-status", action="append", choices=("verified", "partial", "failed"), default=[],
        help="Check only rows with one of these stored audit statuses (repeatable)",
    )
    parser.add_argument("--samples", type=int, default=20, help="Maximum candidate examples in output")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only")
    parser.add_argument("--check-katex", action="store_true", help="Also syntax-check every populated display field with KaTeX")
    parser.add_argument(
        "--check-semantics", action="store_true",
        help="Also reject display fields that omit or alter source prose, formula boundaries, numbers, or operators",
    )
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL") or "postgresql://algo:algo_password@127.0.0.1:5434/algo_content"
    engine = create_engine(db_url)
    where = "tm.is_active = true"
    params: dict[str, Any] = {}
    if args.task_id:
        where += " AND tm.id = ANY(:task_ids)"
        params["task_ids"] = args.task_id
    if args.latex_status:
        where += " AND tm.latex_status = ANY(:latex_statuses)"
        params["latex_statuses"] = args.latex_status

    sql = text(f"""
        SELECT tm.id, tm.question_text, tm.question_latex,
               tm.correct_answer, tm.correct_answer_latex,
               tm.answer_options, tm.answer_options_latex, tm.distractor_meta, tm.latex_status
        FROM tasks_master tm
        WHERE {where}
        ORDER BY tm.id
    """)

    summary: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    total = 0
    tasks_with_issues = 0
    with engine.connect() as conn:
        for db_row in conn.execute(sql, params):
            if args.limit and total >= args.limit:
                break
            total += 1
            row = {
                "id": db_row[0], "question_text": db_row[1], "question_latex": db_row[2],
                "correct_answer": db_row[3], "correct_answer_latex": db_row[4],
                "answer_options": db_row[5], "answer_options_latex": db_row[6],
                "distractor_meta": db_row[7], "latex_status": db_row[8],
            }
            issues = validate_task(
                row,
                check_katex=args.check_katex,
                check_semantics=args.check_semantics,
            )
            if issues:
                tasks_with_issues += 1
            for issue in issues:
                summary[issue] += 1
            actual = expected_status(issues)
            stored = str(row["latex_status"] or "null")
            if stored != actual:
                summary[f"status_mismatch.{stored}_to_{actual}"] += 1
            if (issues or stored != actual) and len(samples) < args.samples:
                samples.append({"task_id": row["id"], "stored_status": stored, "expected_status": actual, "issues": issues})

    report = {
        "mode": "read_only",
        "tasks_checked": total,
        "tasks_with_issues": tasks_with_issues,
        "issue_counts": dict(sorted(summary.items())),
        "samples": samples,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("READ-ONLY: no database rows were modified")
        print(f"Tasks checked: {total}")
        print("Issue counts:")
        for issue, count in sorted(summary.items()):
            print(f"  {count:>6}  {issue}")
        print("Samples:")
        for sample in samples:
            print(f"  {sample['task_id']} [{sample['stored_status']} → {sample['expected_status']}]: {', '.join(sample['issues']) or 'status only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
