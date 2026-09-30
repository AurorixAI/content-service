"""Reversible, owner-approved deactivation of manually reviewed broken tasks.

Nothing is deleted.  Each row gets is_active=false plus provenance in tags
(deactivated_reason / deactivated_at follow the existing convention; batch
and approver keys make the whole batch reversible with one statement:

  UPDATE tasks_master SET is_active = true,
         tags = tags - 'deactivated_reason' - 'deactivated_at' - 'deactivated_by'
                     - 'deactivation_batch' - 'deactivation_approved_by'
  WHERE tags->>'deactivation_batch' = '<batch>';
"""
import argparse
import json
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

parser = argparse.ArgumentParser()
parser.add_argument("--batch-file", required=True)
parser.add_argument("--batch-id", required=True)
parser.add_argument("--execute", action="store_true")
parser.add_argument("--approved-by", default="product-owner-chat-2026-09-23")
args = parser.parse_args()

batch = json.load(open(args.batch_file))
ids = sorted(batch)
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

engine = create_engine(os.environ["DATABASE_URL"])
with engine.begin() as conn:
    rows = conn.execute(
        text("SELECT id, is_active FROM tasks_master WHERE id = ANY(:ids) FOR UPDATE"),
        {"ids": ids},
    ).fetchall()
    found = {r[0]: r[1] for r in rows}
    missing = [i for i in ids if i not in found]
    inactive = [i for i in ids if found.get(i) is False]
    if missing or inactive:
        raise SystemExit(f"SAFETY ABORT: missing={missing[:10]} already_inactive={inactive[:10]}")

    before_active = conn.execute(text("SELECT count(*) FROM tasks_master WHERE is_active")).scalar()
    print(f"batch={args.batch_id} tasks={len(ids)} active_before={before_active}")

    updated = 0
    for tid in ids:
        res = conn.execute(text("""
            UPDATE tasks_master
            SET is_active = false,
                updated_at = now(),
                tags = COALESCE(tags, '{}'::jsonb) || jsonb_build_object(
                    'deactivated_reason', CAST(:reason AS text),
                    'deactivated_at', CAST(:at AS text),
                    'deactivated_by', 'claude-manual-review',
                    'deactivation_batch', CAST(:batch AS text),
                    'deactivation_approved_by', CAST(:appr AS text))
            WHERE id = :id AND is_active
        """), {"id": tid, "reason": batch[tid], "at": now, "batch": args.batch_id, "appr": args.approved_by})
        updated += res.rowcount

    after_active = conn.execute(text("SELECT count(*) FROM tasks_master WHERE is_active")).scalar()
    print(f"updated={updated} active_after={after_active} delta={before_active - after_active}")
    if updated != len(ids) or before_active - after_active != len(ids):
        raise SystemExit("SAFETY ABORT: row count mismatch, rolling back")

    if not args.execute:
        print("[DRY RUN] rolling back, nothing written")
        conn.rollback()
    else:
        print("COMMITTED")
