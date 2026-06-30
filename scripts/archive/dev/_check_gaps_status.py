#!/usr/bin/env python3
"""One-off status check for G8 gaps-only run."""
import os
import sys

sys.path.insert(0, "/app" if os.path.isdir("/app") else os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

from scripts.run_smart_verify import fetch_tasks


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.connect() as conn:
        pending = conn.execute(
            text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 8
                  AND COALESCE(NULLIF(tm.tags->>'smart_verify_status', ''), 'pending') = 'pending'
            """)
        ).scalar()
        verified = conn.execute(
            text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 8
                  AND tm.tags->>'smart_verify_status' IN (
                    'verified_match', 'verified_corrected', 'generated_from_scratch'
                  )
            """)
        ).scalar()
        failed = conn.execute(
            text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 8
                  AND tm.tags->>'smart_verify_status' IN ('failed_at_llm', 'failed_at_sympy')
            """)
        ).scalar()
        recent = conn.execute(
            text("""
                SELECT tm.id, tm.tags->>'smart_verify_status' AS sv,
                       jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) AS dist,
                       tm.updated_at
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 8
                  AND tm.updated_at > NOW() - INTERVAL '6 hours'
                  AND tm.tags ? 'smart_verify_status'
                ORDER BY tm.updated_at DESC
                LIMIT 12
            """)
        ).fetchall()

    queue = fetch_tasks(
        engine, levels=(8,), limit=200, task_id=None, reprocess=False, gaps_only=True
    )

    print(f"pending: {pending}  |  verified: {verified}  |  failed: {failed}  |  gaps queue: {len(queue)}")
    print("\nRecent updates (6h):")
    for r in recent:
        print(f"  {r.id:45} sv={r.sv} dist={r.dist}  {r.updated_at}")
    print("\nGaps queue (all):")
    for r in queue:
        tags = r.tags or {}
        sv = tags.get("smart_verify_status", "pending")
        dist = len(r.distractor_meta or [])
        err = (tags.get("smart_verify_error") or tags.get("distractor_error") or "")[:50]
        regen = tags.get("distractor_regen_pending")
        print(f"  {r.id:40} {r.answer_type:12} sv={sv} dist={dist} regen={regen} err={err}")


if __name__ == "__main__":
    main()
