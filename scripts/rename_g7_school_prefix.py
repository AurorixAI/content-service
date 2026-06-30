#!/usr/bin/env python3
"""
Rename mis-prefixed G7 school ALG tasks: G7_TB_* → G7_ALG_*.

Selection (all must hold):
  1. Linked in textbook_tasks to school textbook_id (Школьное издание G7)
  2. NOT linked to Makarychev textbook_id (zero overlap in current DB)
  3. tasks_master.id starts with G7_TB_
  4. source_reference contains school textbook UUID (extra proof)
  5. Target G7_ALG_* id does not already exist

Usage:
  python scripts/rename_g7_school_prefix.py --dry-run
  python scripts/rename_g7_school_prefix.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings

log = logging.getLogger("rename_g7_school_prefix")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Алгебра 7 — Школьное издание
SCHOOL_TEXTBOOK_ID = "4b19752a-3d54-4538-b6a6-26ce1fbb48fd"
MAKARYCHEV_TEXTBOOK_ID = "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f"


def _proposed_id(old_id: str) -> str:
    if not old_id.startswith("G7_TB_"):
        raise ValueError(f"unexpected id: {old_id}")
    return "G7_ALG_" + old_id[6:]  # G7_TB_ → G7_ALG_


def fetch_candidates(conn) -> list[dict]:
    rows = conn.execute(
        text("""
            SELECT tm.id AS old_id,
                   tm.source_reference,
                   tm.tags
            FROM tasks_master tm
            WHERE tm.id LIKE 'G7_TB_%'
              AND EXISTS (
                SELECT 1 FROM textbook_tasks tt
                WHERE tt.task_id = tm.id AND tt.textbook_id = :school
              )
              AND NOT EXISTS (
                SELECT 1 FROM textbook_tasks tt
                WHERE tt.task_id = tm.id AND tt.textbook_id = :mak
              )
              AND (
                tm.source_reference IS NULL
                OR tm.source_reference LIKE :school_ref || '%'
              )
            ORDER BY tm.id
        """),
        {
            "school": SCHOOL_TEXTBOOK_ID,
            "mak": MAKARYCHEV_TEXTBOOK_ID,
            "school_ref": SCHOOL_TEXTBOOK_ID,
        },
    ).mappings().all()
    out: list[dict] = []
    for r in rows:
        old = r["old_id"]
        new = _proposed_id(old)
        out.append(
            {
                "old_id": old,
                "new_id": new,
                "source_reference": r["source_reference"],
            }
        )
    return out


def validate(conn, candidates: list[dict]) -> list[str]:
    errors: list[str] = []
    new_ids = [c["new_id"] for c in candidates]
    if len(new_ids) != len(set(new_ids)):
        errors.append("duplicate proposed new_ids in batch")

    if candidates:
        existing = conn.execute(
            text("SELECT id FROM tasks_master WHERE id = ANY(:ids)"),
            {"ids": new_ids},
        ).fetchall()
        if existing:
            errors.append(f"collision: {len(existing)} target ids already exist")

    # school TB misnamed not in candidates
    extra = conn.execute(
        text("""
            SELECT count(*) FROM tasks_master tm
            JOIN textbook_tasks tt ON tt.task_id = tm.id AND tt.textbook_id = :school
            WHERE tm.id LIKE 'G7_TB_%'
              AND NOT EXISTS (
                SELECT 1 FROM textbook_tasks m
                WHERE m.task_id = tm.id AND m.textbook_id = :mak
              )
        """),
        {"school": SCHOOL_TEXTBOOK_ID, "mak": MAKARYCHEV_TEXTBOOK_ID},
    ).scalar()
    if extra != len(candidates):
        errors.append(f"candidate count mismatch: sql={extra} parsed={len(candidates)}")

    return errors


def apply_rename(conn, old_id: str, new_id: str) -> None:
    tags_row = conn.execute(
        text("SELECT tags FROM tasks_master WHERE id = :id"),
        {"id": old_id},
    ).scalar()
    tags = dict(tags_row or {})
    tags["id_renamed_from"] = old_id
    tags["source_textbook"] = "school_alg_g7"
    tags["rename_script"] = "rename_g7_school_prefix"
    tags_json = json.dumps(tags, ensure_ascii=False)

    # FK textbook_tasks.task_id → tasks_master.id has no ON UPDATE CASCADE.
    # Copy row with new PK, repoint children, delete old row.
    conn.execute(
        text("""
            INSERT INTO tasks_master (
                id, skill_id, question_text, question_latex, question_image_url,
                answer_type, correct_answer, correct_answer_latex, sympy_solution,
                answer_options, difficulty, irt_discrimination, irt_difficulty, irt_guessing,
                distractor_meta, is_active, created_at, updated_at, toc_id, cognitive_load,
                verification_status, source_type, source_reference, tags, is_star, task_category
            )
            SELECT
                :new_id, skill_id, question_text, question_latex, question_image_url,
                answer_type, correct_answer, correct_answer_latex, sympy_solution,
                answer_options, difficulty, irt_discrimination, irt_difficulty, irt_guessing,
                distractor_meta, is_active, created_at, NOW(), toc_id, cognitive_load,
                verification_status, source_type, source_reference,
                cast(:tags AS jsonb), is_star, task_category
            FROM tasks_master
            WHERE id = :old_id
        """),
        {"new_id": new_id, "old_id": old_id, "tags": tags_json},
    )
    conn.execute(
        text("UPDATE task_figure_refs SET task_id = :new WHERE task_id = :old"),
        {"old": old_id, "new": new_id},
    )
    conn.execute(
        text("UPDATE textbook_tasks SET task_id = :new WHERE task_id = :old"),
        {"old": old_id, "new": new_id},
    )
    conn.execute(
        text("DELETE FROM tasks_master WHERE id = :old"),
        {"old": old_id},
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        candidates = fetch_candidates(conn)
        errors = validate(conn, candidates)

    log.info("Candidates: %d (G7_TB_* → G7_ALG_*)", len(candidates))
    for c in candidates[:5]:
        log.info("  %s → %s", c["old_id"], c["new_id"])
    if len(candidates) > 5:
        log.info("  ... +%d more", len(candidates) - 5)

    if errors:
        for e in errors:
            log.error("VALIDATION: %s", e)
        return 1

    manifest = {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "school_textbook_id": SCHOOL_TEXTBOOK_ID,
        "makarychev_textbook_id": MAKARYCHEV_TEXTBOOK_ID,
        "count": len(candidates),
        "mapping": candidates,
    }

    if args.dry_run:
        log.info("DRY RUN OK — no changes written")
        return 0

    with engine.begin() as conn:
        for c in candidates:
            apply_rename(conn, c["old_id"], c["new_id"])

    log.info("Renamed %d tasks", len(candidates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
