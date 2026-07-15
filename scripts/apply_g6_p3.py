#!/usr/bin/env python3
"""P3 apply: upgrade independently-recomputed G6 answers llm_fallback -> computed.

Reads g6_p3_verified.json (produced by verify_g6_llm_fallback.py). For each task
that is STILL answer_canonical_source=llm_fallback, marks it math-confirmed:
  answer_canonical_source = 'computed'
  p3_verified = 'true'
  p3_category / p3_proof  (audit trail)
Does NOT change correct_answer or distractors.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings

log = logging.getLogger("apply_g6_p3")
logging.basicConfig(level=logging.INFO, format="%(message)s")

VERIFIED_JSON = Path("/app/scripts/g6_p3_verified.json")


def _tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(raw or "{}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = json.loads(VERIFIED_JSON.read_text())
    by_id = {it["id"]: it for it in items}
    ids = list(by_id)
    log.info("Loaded %d verified P3 tasks", len(ids))

    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tm.id, tm.tags, tm.correct_answer
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 6 AND tm.id = ANY(:ids)
                """
            ),
            {"ids": ids},
        ).mappings().all()

    found = {r["id"] for r in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        log.warning("MISSING (%d): %s", len(missing), missing)

    n_upd = n_skip = 0
    for r in rows:
        tid = r["id"]
        tags = _tags(r["tags"])
        src = tags.get("answer_canonical_source")
        if src != "llm_fallback":
            log.info("  SKIP %s (source=%s, not llm_fallback)", tid, src)
            n_skip += 1
            continue
        it = by_id[tid]
        tags["answer_canonical_source"] = "computed"
        tags["answer_canonical_source_prev"] = "llm_fallback"
        tags["p3_verified"] = "true"
        tags["p3_category"] = it["cat"]
        tags["p3_proof"] = it["proof"][:200]
        tags["answer_math_confirmed"] = True
        if args.dry_run:
            log.info("  [dry] %s  [%s] %s", tid, it["cat"], it["proof"][:60])
            n_upd += 1
            continue
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE tasks_master
                    SET tags = cast(:tags AS jsonb), updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {"id": tid, "tags": json.dumps(tags, ensure_ascii=False)},
            )
        log.info("  OK  %s  [%s]", tid, it["cat"])
        n_upd += 1

    log.info("Done: upgraded=%d skipped=%d missing=%d", n_upd, n_skip, len(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
