#!/usr/bin/env python3
"""
Grade quality cleanup — compound tags, orphan OCR tails, repair flags.

Usage:
  python scripts/grade_quality_cleanup.py --class-level 8 --dry-run
  python scripts/grade_quality_cleanup.py --class-level 7 --steps 1,2,6
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.compound_detect import detect_compound
from src.pipeline.compound_repair import (
    CompoundIssue,
    apply_orphan_trim_tags,
    classify_compound_issue,
    clear_compound_block_tags,
    mark_content_repair,
    sync_compound_tags_from_detect,
    trim_orphan_question_tail,
)
from scripts.split_compound_tasks import split_task

log = logging.getLogger("grade_quality_cleanup")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def fetch_g8_tasks(engine, class_level: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags,
                       tt.exercise_number
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                LEFT JOIN textbook_tasks tt
                  ON tt.task_id = tm.id AND tt.textbook_id = tb.textbook_id
                WHERE tb.class_level = :level
                ORDER BY tm.id
            """),
            {"level": class_level},
        ).mappings().all()
    return [dict(r) for r in rows]


def persist_task(engine, task_id: str, *, question_text: str | None = None, tags: dict) -> None:
    params: dict = {
        "id": task_id,
        "tags": json.dumps(tags, ensure_ascii=False),
    }
    if question_text is not None:
        sql = """
            UPDATE tasks_master
            SET question_text = :q, tags = cast(:tags AS jsonb)
            WHERE id = :id
        """
        params["q"] = question_text
    else:
        sql = """
            UPDATE tasks_master
            SET tags = cast(:tags AS jsonb)
            WHERE id = :id
        """
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def step1_clear_stale_tags(engine, rows: list[dict], dry_run: bool) -> int:
    n = 0
    for row in rows:
        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        if tags.get("needs_compound_split") is not True:
            continue
        st = split_task(row)
        issue = classify_compound_issue(
            task_id=row["id"],
            question_text=row["question_text"] or "",
            correct_answer=row["correct_answer"] or "",
            answer_type=row["answer_type"] or "",
            tags=tags,
            split_item_count=len(st.items),
            split_second_answer_empty=bool(
                st.items and len(st.items) >= 2 and not (st.items[1]["correct_answer"] or "").strip()
            ),
        )
        if issue.issue != CompoundIssue.STALE_TAG:
            continue
        new_tags = sync_compound_tags_from_detect(
            tags,
            task_id=row["id"],
            question_text=row["question_text"] or "",
            correct_answer=row["correct_answer"] or "",
            answer_type=row["answer_type"] or "",
        )
        log.info("  [1] stale tag cleared: %s", row["id"])
        if not dry_run:
            persist_task(engine, row["id"], tags=new_tags)
        n += 1
    log.info("Step 1: cleared %d stale compound tags", n)
    return n


def step2_orphan_trim(engine, rows: list[dict], dry_run: bool) -> int:
    n = 0
    for row in rows:
        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        st = split_task(row)
        issue = classify_compound_issue(
            task_id=row["id"],
            question_text=row["question_text"] or "",
            correct_answer=row["correct_answer"] or "",
            answer_type=row["answer_type"] or "",
            tags=tags,
            split_item_count=len(st.items),
            split_second_answer_empty=bool(
                st.items and len(st.items) >= 2 and not (st.items[1]["correct_answer"] or "").strip()
            ),
        )
        if issue.issue != CompoundIssue.ORPHAN_TAIL:
            continue
        q = row["question_text"] or ""
        trimmed = issue.trimmed_question or trim_orphan_question_tail(q)[0]
        if trimmed == q:
            continue
        log.info("  [2] orphan trim: %s", row["id"])
        log.info("       was: %s", q[:90].replace("\n", " "))
        log.info("       now: %s", trimmed[:90].replace("\n", " "))
        if not dry_run:
            new_tags = apply_orphan_trim_tags(tags)
            persist_task(engine, row["id"], question_text=trimmed, tags=new_tags)
        n += 1
    log.info("Step 2: trimmed %d orphan tails (reset to pending)", n)
    return n


def step6_broken_batch(engine, rows: list[dict], dry_run: bool) -> int:
    n = 0
    for row in rows:
        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        st = split_task(row)
        issue = classify_compound_issue(
            task_id=row["id"],
            question_text=row["question_text"] or "",
            correct_answer=row["correct_answer"] or "",
            answer_type=row["answer_type"] or "",
            tags=tags,
            split_item_count=len(st.items),
        )
        if issue.issue != CompoundIssue.BROKEN_BATCH:
            continue
        if tags.get("needs_content_repair"):
            continue
        log.info("  [6] content repair: %s — %s", row["id"], issue.detail)
        log.info("       Q: %s", (row["question_text"] or "")[:100].replace("\n", " "))
        log.info("       A: %s", (row["correct_answer"] or "")[:80])
        if not dry_run:
            new_tags = mark_content_repair(tags, reason=issue.detail)
            persist_task(engine, row["id"], tags=new_tags)
        n += 1
    log.info("Step 6: tagged %d broken batch for content repair", n)
    return n


def step3_report_dist_gaps(engine, class_level: int) -> int:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, jsonb_array_length(COALESCE(tm.distractor_meta,'[]')) d
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags->>'smart_verify_status' IN (
                    'verified_match','verified_corrected','generated_from_scratch'
                  )
                  AND jsonb_array_length(COALESCE(tm.distractor_meta,'[]')) < 2
                  AND tm.answer_type NOT IN ('text','open_text','coordinate')
            """),
            {"level": class_level},
        ).mappings().all()
    for r in rows:
        log.info("  [3] dist gap: %s (dist=%s)", r["id"], r["d"])
    log.info("Step 3: %d dist gaps — run gaps-only after cleanup", len(rows))
    return len(rows)


def step4_report_failed(engine, class_level: int) -> int:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.answer_type, tm.tags->>'smart_verify_error' err
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags->>'smart_verify_status' IN ('failed_at_llm','failed_at_sympy')
                ORDER BY tm.id
            """),
            {"level": class_level},
        ).mappings().all()
    for r in rows:
        log.info("  [4] failed: %s (%s) %s", r["id"], r["answer_type"], (r["err"] or "")[:60])
    log.info("Step 4: %d failed — run retry-failed after cleanup", len(rows))
    return len(rows)


def step5_report_human(engine, class_level: int) -> int:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.answer_type, tm.tags->>'smart_verify_reason' reason
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                  AND tm.tags->>'smart_verify_status' = 'needs_human_review'
                ORDER BY tm.id
            """),
            {"level": class_level},
        ).mappings().all()
    log.info("Step 5: %d human review (manual):", len(rows))
    for r in rows[:10]:
        log.info("  [5] %s (%s) %s", r["id"], r["answer_type"], (r["reason"] or "-")[:50])
    if len(rows) > 10:
        log.info("  ... +%d more", len(rows) - 10)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="G8 quality cleanup pipeline")
    ap.add_argument("--class-level", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--steps", default="all", help="Comma list or 'all'")
    args = ap.parse_args()

    steps = {"1", "2", "3", "4", "5", "6"} if args.steps == "all" else {s.strip() for s in args.steps.split(",")}

    engine = create_engine(get_settings().database_url)
    rows = fetch_g8_tasks(engine, args.class_level)

    log.info("G8 quality cleanup | level=%d | tasks=%d | dry_run=%s", args.class_level, len(rows), args.dry_run)
    log.info("Steps: %s", ",".join(sorted(steps)))

    if "1" in steps:
        step1_clear_stale_tags(engine, rows, args.dry_run)
        if not args.dry_run:
            rows = fetch_g8_tasks(engine, args.class_level)
    if "2" in steps:
        step2_orphan_trim(engine, rows, args.dry_run)
        if not args.dry_run:
            rows = fetch_g8_tasks(engine, args.class_level)
    if "6" in steps:
        step6_broken_batch(engine, rows, args.dry_run)
    if "3" in steps:
        step3_report_dist_gaps(engine, args.class_level)
    if "4" in steps:
        step4_report_failed(engine, args.class_level)
    if "5" in steps:
        step5_report_human(engine, args.class_level)

    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
