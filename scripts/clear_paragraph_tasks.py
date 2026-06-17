#!/usr/bin/env python3
"""Delete digitized tasks for specific paragraph numbers (re-extract clean).

Usage:
    docker exec content-worker python /app/scripts/clear_paragraph_tasks.py \\
        --textbook-id 69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f --paragraphs 1,2,3
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--textbook-id", required=True)
    ap.add_argument("--paragraphs", required=True, help="Comma-separated, e.g. 1,2,3")
    args = ap.parse_args()
    nums = [p.strip() for p in args.paragraphs.split(",") if p.strip()]

    engine = create_engine(get_settings().database_url)
    with engine.begin() as conn:
        r = conn.execute(
            text("""
                DELETE FROM tasks_master tm
                USING textbook_tasks tt
                WHERE tt.textbook_id = CAST(:tid AS UUID)
                  AND tt.task_id = tm.id
                  AND tt.paragraph_number = ANY(:nums)
            """),
            {"tid": args.textbook_id, "nums": nums},
        )
        conn.execute(
            text("""
                DELETE FROM textbook_tasks
                WHERE textbook_id = CAST(:tid AS UUID)
                  AND paragraph_number = ANY(:nums)
            """),
            {"tid": args.textbook_id, "nums": nums},
        )
    print(f"[OK] Cleared tasks for paragraphs {nums} ({r.rowcount} tasks_master rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
