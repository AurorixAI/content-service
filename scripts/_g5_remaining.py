#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text
from src.core.config import get_settings

e = create_engine(get_settings().database_url)
with e.connect() as c:
    print("=== DIST GAP (non-text) ===")
    for r in c.execute(text("""
        SELECT tm.id, tm.answer_type,
               jsonb_array_length(COALESCE(tm.distractor_meta,'[]'::jsonb)) d,
               left(tm.correct_answer,50) a
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 5
          AND jsonb_array_length(COALESCE(tm.distractor_meta,'[]'::jsonb)) < 2
          AND tm.answer_type NOT IN ('text','open_text','coordinate')
        ORDER BY tm.id
    """)):
        print(f"  {r.id} [{r.answer_type}] dist={r.d} | {r.a}")

    print("\n=== REGEN_PENDING ===")
    for r in c.execute(text("""
        SELECT tm.id, tm.answer_type,
               jsonb_array_length(COALESCE(tm.distractor_meta,'[]'::jsonb)) d
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 5 AND tm.tags ? 'distractor_regen_pending'
        ORDER BY tm.id
    """)):
        print(f"  {r.id} [{r.answer_type}] dist={r.d}")

    print("\n=== CONTENT_REPAIR ===")
    for r in c.execute(text("""
        SELECT tm.id, tm.correct_answer, tm.tags->>'smart_verify_error' e
        FROM tasks_master tm
        WHERE tm.tags->>'smart_verify_status' = 'needs_content_repair'
          AND tm.id LIKE 'G5_%'
    """)):
        print(f"  {r.id} | {r.correct_answer[:50]} | {r.e}")

    print("\n=== NO smart_verify_run_id (never reprocess) ===")
    n = c.execute(text("""
        SELECT count(*) FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 5 AND NOT (tm.tags ? 'smart_verify_run_id')
    """)).scalar()
    print(f"  {n}")

    print("\n=== GENERATED_FROM_SCRATCH ===")
    for r in c.execute(text("""
        SELECT tm.id, left(tm.correct_answer,60) a
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 5
          AND tm.tags->>'smart_verify_status' = 'generated_from_scratch'
    """)):
        print(f"  {r.id} | {r.a}")
