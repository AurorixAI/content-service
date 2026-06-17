"""Shared verify-answer + distractor pass for DB tasks (grades 5–8)."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.pipeline.distractors import generate_distractors
from src.pipeline.models import ExtractedTask

log = logging.getLogger(__name__)


def fetch_tasks_for_verify(
    engine: Engine,
    *,
    class_level: int | None = None,
    class_levels: tuple[int, ...] | None = None,
    textbook_id: str | None = None,
) -> list[tuple]:
    """Tasks needing verify and/or distractor (re)generation."""
    levels = class_levels or ((class_level,) if class_level is not None else ())
    if not levels:
        raise ValueError("class_level or class_levels required")

    level_sql = ", ".join(str(int(x)) for x in levels)
    tb_filter = ""
    params: dict[str, Any] = {}
    if textbook_id:
        tb_filter = "AND tb.textbook_id = CAST(:textbook_id AS UUID)"
        params["textbook_id"] = textbook_id

    sql = f"""
        SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
               tm.distractor_meta
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level IN ({level_sql})
          AND tm.correct_answer IS NOT NULL AND trim(tm.correct_answer) != ''
          AND COALESCE(tm.tags->>'answer_mismatch', 'false') != 'true'
          AND COALESCE(tm.tags->>'verify_unresolved', 'false') != 'true'
          AND COALESCE(tm.tags->>'verify_conflict', 'false') != 'true'
          AND COALESCE(tm.tags->>'smart_verify_status', '') NOT IN (
            'verified_match', 'verified_corrected', 'generated_from_scratch'
          )
          AND (
            COALESCE(tm.tags->>'answer_gemini_verified', 'false') = 'false'
            OR COALESCE(tm.tags->>'distractor_regen_pending', 'false') = 'true'
            OR (
              tm.distractor_meta IS NULL
              OR tm.distractor_meta::text IN ('null', '[]')
            )
          )
          {tb_filter}
        ORDER BY tb.class_level, tm.answer_type, tm.id
    """
    with engine.connect() as conn:
        return conn.execute(text(sql), params).fetchall()


def _parse_tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _parse_dmeta(raw) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def persist_verify_result(
    engine: Engine,
    task_id: str,
    result: ExtractedTask,
    old_tags: dict,
    *,
    previous_answer: str = "",
) -> str:
    """
    Persist verify/distractor outcome. Returns action label for stats.

    Rules:
      - New distractors → save answer + tags + distractor_meta
      - answer_mismatch → clear distractors
      - answer corrected → always clear stale distractors if regen failed
      - verified match only → update answer/tags, keep existing distractors
    """
    tags = dict(old_tags)
    tags.update(result.tags or {})
    new_answer = (result.answer_raw or previous_answer or "").strip()

    mode = tags.get("answer_verify_mode", "")
    if mode in ("match", "sympy_match", "skipped", "skipped_type", "corrected_sympy"):
        for stale in ("verify_unresolved", "verify_conflict", "answer_mismatch", "verify_reverted"):
            tags.pop(stale, None)

    tags_json = json.dumps(tags, ensure_ascii=False)

    if result.distractor_meta:
        dmeta_json = json.dumps(result.distractor_meta, ensure_ascii=False)
        tags.pop("distractor_regen_pending", None)
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        tags = cast(:tags as jsonb),
                        distractor_meta = cast(:dmeta as jsonb)
                    WHERE id = :id
                """),
                {"id": task_id, "ans": new_answer, "tags": tags_json, "dmeta": dmeta_json},
            )
        return "new_dist"

    if tags.get("answer_mismatch"):
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        tags = cast(:tags as jsonb),
                        distractor_meta = '[]'::jsonb
                    WHERE id = :id
                """),
                {"id": task_id, "ans": new_answer, "tags": tags_json},
            )
        return "mismatch"

    if tags.get("verify_unresolved") or tags.get("answer_verify_mode") == "dual_failed":
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        tags = cast(:tags as jsonb)
                    WHERE id = :id
                """),
                {"id": task_id, "ans": new_answer, "tags": tags_json},
            )
        return "unresolved"

    if tags.get("verify_conflict"):
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        tags = cast(:tags as jsonb)
                    WHERE id = :id
                """),
                {"id": task_id, "ans": new_answer, "tags": tags_json},
            )
        return "conflict"

    if tags.get("answer_corrected_by_gemini"):
        tags["distractor_regen_pending"] = True
        tags_json = json.dumps(tags, ensure_ascii=False)
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        tags = cast(:tags as jsonb),
                        distractor_meta = '[]'::jsonb
                    WHERE id = :id
                """),
                {"id": task_id, "ans": new_answer, "tags": tags_json},
            )
        return "corrected_no_dist"

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE tasks_master
                SET correct_answer = :ans,
                    tags = cast(:tags as jsonb)
                WHERE id = :id
            """),
            {"id": task_id, "ans": new_answer, "tags": tags_json},
        )
    if tags.get("answer_gemini_verified"):
        return "verified_kept"
    return "other"


def run_verify_distractor_pass(
    engine: Engine,
    rows: list[tuple],
    *,
    label: str = "verify",
) -> dict[str, int]:
    stats = {
        "new_dist": 0,
        "verified_kept": 0,
        "corrected": 0,
        "corrected_no_dist": 0,
        "mismatch": 0,
        "unresolved": 0,
        "conflict": 0,
        "errors": 0,
    }

    for task_id, question, answer, atype, dmeta_raw in rows:
        with engine.connect() as conn:
            tag_row = conn.execute(
                text("SELECT tags FROM tasks_master WHERE id = :id"),
                {"id": task_id},
            ).fetchone()
        old_tags = _parse_tags(tag_row[0] if tag_row else {})

        et = ExtractedTask(
            temp_id=task_id,
            question_text=question or "",
            answer_raw=answer or "",
            answer_type=atype or "exact_number",
            distractor_meta=_parse_dmeta(dmeta_raw) or None,
        )
        try:
            result = generate_distractors(et)
        except Exception as exc:
            log.debug("  %s error: %s", task_id, exc)
            stats["errors"] += 1
            continue

        if (result.tags or {}).get("answer_corrected_by_gemini"):
            stats["corrected"] += 1
            log.info("  ↻ %s answer corrected", task_id)

        action = persist_verify_result(
            engine, task_id, result, old_tags, previous_answer=answer or ""
        )
        stats[action] = stats.get(action, 0) + 1
        if action == "new_dist" and stats["new_dist"] % 50 == 0:
            log.info("  ... %d %s", stats["new_dist"], label)

    log.info(
        "  %s: new_dist=%d verified_kept=%d corrected=%d corrected_pending=%d "
        "mismatch=%d unresolved=%d conflict=%d errors=%d",
        label,
        stats["new_dist"],
        stats["verified_kept"],
        stats["corrected"],
        stats["corrected_no_dist"],
        stats["mismatch"],
        stats["unresolved"],
        stats["conflict"],
        stats["errors"],
    )
    return stats
