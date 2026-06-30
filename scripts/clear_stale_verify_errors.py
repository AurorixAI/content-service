#!/usr/bin/env python3
"""Clear stale smart_verify_error on already-verified G8 tasks."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 8
                  AND tm.tags->>'smart_verify_status' IN (
                    'verified_match', 'verified_corrected', 'generated_from_scratch'
                  )
                  AND tm.tags ? 'smart_verify_error'
            """)
        ).fetchall()

    cleared = 0
    for row in rows:
        tags = dict(row.tags or {})
        tags.pop("smart_verify_error", None)
        tags_json = json.dumps(tags, ensure_ascii=False)
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET tags = cast(:tags as jsonb)
                    WHERE id = :id
                """),
                {"id": row.id, "tags": tags_json},
            )
        cleared += 1
        print(f"cleared: {row.id}")

    print(f"Done: cleared {cleared} tasks")


if __name__ == "__main__":
    main()
