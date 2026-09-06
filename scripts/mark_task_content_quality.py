#!/usr/bin/env python3
"""Safely classify mathematically invalid tasks without editing source content.

``verification_status`` is the canonical content-quality status.  A rejected
task is deactivated so student-facing task selectors cannot return it.  The
specific, auditable reason lives in ``tags.content_quality``; ``latex_status``
is deliberately left untouched because a faithful LaTeX projection and an
invalid mathematical source are independent facts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Iterable

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

CONTENT_STATUS = "mathematically_invalid"
REVIEW_SOURCE = "professional_manual_audit"


def parse_findings(values: Iterable[str]) -> dict[str, str]:
    findings: dict[str, str] = {}
    for value in values:
        task_id, separator, reason = str(value).partition("::")
        task_id, reason = task_id.strip(), reason.strip()
        if not separator or not task_id or not reason:
            raise ValueError("finding must use TASK_ID::REASON with both parts non-empty")
        if task_id in findings and findings[task_id] != reason:
            raise ValueError(f"conflicting reasons supplied for task {task_id}")
        findings[task_id] = reason
    if not findings:
        raise ValueError("at least one --finding is required")
    return findings


def source_fingerprint(row) -> str:
    payload = {
        "question_text": row.question_text or "",
        "correct_answer": row.correct_answer or "",
        "distractor_meta": row.distractor_meta,
        "answer_options": row.answer_options,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_tasks(conn, task_ids: list[str], *, lock: bool = False):
    lock_sql = " FOR UPDATE" if lock else ""
    return conn.execute(text("""
        SELECT id, question_text, correct_answer, distractor_meta, answer_options,
               verification_status, latex_status, is_active, tags
        FROM tasks_master
        WHERE id = ANY(:task_ids)
        ORDER BY id
    """ + lock_sql), {"task_ids": task_ids}).fetchall()


def load_existing_invalid_tasks(conn, *, lock: bool = False):
    """Return only audited invalid tasks whose public state is stale.

    A few historical rows already carry the professional
    ``content_quality.mathematically_invalid`` finding but were left in a
    student-visible verification state by older scripts.  This selector is
    deliberately driven by that existing audit marker; it never tries to
    infer mathematical invalidity from an LLM result.
    """
    lock_sql = " FOR UPDATE" if lock else ""
    return conn.execute(text("""
        SELECT id, question_text, correct_answer, distractor_meta, answer_options,
               verification_status, latex_status, is_active, tags
        FROM tasks_master
        WHERE tags->'content_quality'->>'status' = :content_status
          AND (verification_status <> 'rejected' OR is_active = TRUE)
        ORDER BY id
    """ + lock_sql), {"content_status": CONTENT_STATUS}).fetchall()


def _preview_row(row, *, reason: str) -> dict:
    return {
        "task_id": str(row.id),
        "from_verification_status": row.verification_status,
        "to_verification_status": "rejected",
        "from_is_active": bool(row.is_active),
        "to_is_active": False,
        "latex_status_unchanged": row.latex_status,
        "reason": reason,
        "source_fingerprint": source_fingerprint(row),
    }


def mark_mathematically_invalid(engine, findings: dict[str, str], *, execute: bool) -> list[dict]:
    task_ids = sorted(findings)
    with engine.connect() as conn:
        preview_rows = load_tasks(conn, task_ids)
    found_ids = {str(row.id) for row in preview_rows}
    missing = sorted(set(task_ids) - found_ids)
    if missing:
        raise RuntimeError(f"tasks not found; refusing partial operation: {missing}")

    preview = [_preview_row(row, reason=findings[str(row.id)]) for row in preview_rows]
    if not execute:
        return preview

    reviewed_at = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        locked_rows = load_tasks(conn, task_ids, lock=True)
        before = {str(row.id): source_fingerprint(row) for row in locked_rows}
        if set(before) != set(task_ids):
            raise RuntimeError("task set changed before lock; refusing operation")

        for task_id in task_ids:
            math_audit = {
                "status": CONTENT_STATUS,
                "confidence": "high",
                "reason": findings[task_id],
                "evidence": findings[task_id],
                "review_source": REVIEW_SOURCE,
                "reviewed_at": reviewed_at,
            }
            content_quality = {
                "status": CONTENT_STATUS,
                "reason": findings[task_id],
                "review_source": REVIEW_SOURCE,
                "reviewed_at": reviewed_at,
            }
            conn.execute(text("""
                UPDATE tasks_master
                SET verification_status = 'rejected',
                    is_active = FALSE,
                    tags = jsonb_set(
                        jsonb_set(
                            COALESCE(tags, '{}'::jsonb),
                            '{math_audit}',
                            CAST(:math_audit AS jsonb),
                            TRUE
                        ),
                        '{content_quality}', CAST(:content_quality AS jsonb), TRUE
                    ),
                    updated_at = NOW()
                WHERE id = :task_id
            """), {
                "task_id": task_id,
                "math_audit": json.dumps(math_audit, ensure_ascii=False),
                "content_quality": json.dumps(content_quality, ensure_ascii=False),
            })

        after_rows = load_tasks(conn, task_ids, lock=True)
        after = {str(row.id): source_fingerprint(row) for row in after_rows}
        if before != after:
            raise RuntimeError("canonical source changed; transaction rolled back")
        for row in after_rows:
            content_quality = (row.tags or {}).get("content_quality", {})
            math_audit = (row.tags or {}).get("math_audit", {})
            if (row.verification_status != "rejected" or row.is_active
                    or content_quality.get("status") != CONTENT_STATUS
                    or math_audit.get("status") != CONTENT_STATUS):
                raise RuntimeError(f"post-write verification failed for {row.id}")

    return preview


def sync_existing_mathematically_invalid(engine, *, execute: bool) -> list[dict]:
    """Synchronize only pre-audited invalid rows to the rejected state.

    The raw question, answer, choices, and all LaTeX columns are treated as
    immutable.  We preserve the existing audit reason and record a matching
    ``math_audit`` envelope for operational traceability.
    """
    with engine.connect() as conn:
        preview_rows = load_existing_invalid_tasks(conn)

    def reason_for(row) -> str:
        tags = row.tags or {}
        quality = tags.get("content_quality") or {}
        return str(quality.get("reason") or "Previously audited mathematically invalid task.")

    preview = [_preview_row(row, reason=reason_for(row)) for row in preview_rows]
    if not execute or not preview_rows:
        return preview

    task_ids = [str(row.id) for row in preview_rows]
    with engine.begin() as conn:
        locked_rows = load_existing_invalid_tasks(conn, lock=True)
        locked_ids = [str(row.id) for row in locked_rows]
        if locked_ids != task_ids:
            raise RuntimeError("audited invalid task set changed before lock; refusing operation")

        before_sources = {str(row.id): source_fingerprint(row) for row in locked_rows}
        before_latex = {str(row.id): row.latex_status for row in locked_rows}
        for row in locked_rows:
            tags = row.tags or {}
            quality = tags.get("content_quality") or {}
            reason = reason_for(row)
            math_audit = {
                "status": CONTENT_STATUS,
                "confidence": "high",
                "reason": reason,
                "evidence": reason,
                "review_source": quality.get("review_source") or REVIEW_SOURCE,
                "reviewed_at": quality.get("reviewed_at") or datetime.now(timezone.utc).isoformat(),
            }
            conn.execute(text("""
                UPDATE tasks_master
                SET verification_status = 'rejected',
                    is_active = FALSE,
                    tags = jsonb_set(
                        COALESCE(tags, '{}'::jsonb),
                        '{math_audit}', CAST(:math_audit AS jsonb), TRUE
                    ),
                    updated_at = NOW()
                WHERE id = :task_id
            """), {
                "task_id": str(row.id),
                "math_audit": json.dumps(math_audit, ensure_ascii=False),
            })

        after_rows = load_tasks(conn, task_ids, lock=True)
        after_sources = {str(row.id): source_fingerprint(row) for row in after_rows}
        after_latex = {str(row.id): row.latex_status for row in after_rows}
        if before_sources != after_sources:
            raise RuntimeError("canonical source changed; transaction rolled back")
        if before_latex != after_latex:
            raise RuntimeError("LaTeX state changed; transaction rolled back")
        for row in after_rows:
            tags = row.tags or {}
            if (row.verification_status != "rejected" or row.is_active
                    or (tags.get("content_quality") or {}).get("status") != CONTENT_STATUS
                    or (tags.get("math_audit") or {}).get("status") != CONTENT_STATUS):
                raise RuntimeError(f"post-write verification failed for {row.id}")

    return preview


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--finding", action="append",
        help="Repeatable TASK_ID::REASON classification",
    )
    parser.add_argument(
        "--sync-existing-math-invalid",
        action="store_true",
        help="Synchronize only already audited mathematically_invalid rows to rejected",
    )
    parser.add_argument("--execute", action="store_true", help="Persist after an exact preview")
    args = parser.parse_args()
    if args.sync_existing_math_invalid and args.finding:
        parser.error("--sync-existing-math-invalid cannot be combined with --finding")
    if not args.sync_existing_math_invalid and not args.finding:
        parser.error("provide --finding or --sync-existing-math-invalid")
    if args.finding:
        try:
            findings = parse_findings(args.finding)
        except ValueError as exc:
            parser.error(str(exc))

    db_url = os.environ.get("DATABASE_URL") or "postgresql://algo:algo_password@127.0.0.1:5434/algo_content"
    engine = create_engine(db_url)
    result = (
        sync_existing_mathematically_invalid(engine, execute=args.execute)
        if args.sync_existing_math_invalid
        else mark_mathematically_invalid(engine, findings, execute=args.execute)
    )
    print(json.dumps({"mode": "execute" if args.execute else "dry_run", "tasks": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
