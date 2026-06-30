#!/usr/bin/env python3
"""Clear stale smart_verify_error tags on verified G8 tasks."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings

log = logging.getLogger("fix_g8_stale_tags")
logging.basicConfig(level=logging.INFO, format="%(message)s")

STALE_ERROR_IDS = [
    "G8_TB_9_197.1",
    "G8_TB_9_197.2",
    "G8_TB_9_197.3",
    "G8_TB_9_197.4",
    "G8_TB_10_273.3",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    ok = 0

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, tags FROM tasks_master
                WHERE id = ANY(:ids)
            """),
            {"ids": STALE_ERROR_IDS},
        ).mappings().all()

    for row in rows:
        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        err = tags.pop("smart_verify_error", None)
        if not err:
            continue
        log.info("%s cleared error: %s", row["id"], str(err)[:60])
        if args.dry_run:
            ok += 1
            continue
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE tasks_master SET tags = cast(:tags AS jsonb), updated_at = NOW() WHERE id = :id"),
                {"id": row["id"], "tags": json.dumps(tags, ensure_ascii=False)},
            )
        ok += 1

    log.info("Done: cleared=%d", ok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
