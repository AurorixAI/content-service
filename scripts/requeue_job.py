#!/usr/bin/env python3
"""Re-enqueue a stuck digitization job WITHOUT wiping OCR cache or paragraph counters.

Use instead of reset_for_retry when worker died mid-run but OCR cache is intact.

Usage:
    docker exec content-worker python /app/scripts/requeue_job.py 9e3db10a-887a-4496-8bd9-3c2c896d860d
    docker exec content-worker python /app/scripts/requeue_job.py 9e3db10a-... --full-reset
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, "/app")

from src.core.job_enqueue import enqueue_digitization
from src.core.job_state import JobStateManager


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument(
        "--full-reset",
        action="store_true",
        help="Clear paragraph counters (OCR still uses disk cache if present)",
    )
    args = ap.parse_args()

    state = JobStateManager()
    job = state.get(args.job_id)
    if not job:
        print(f"Job {args.job_id} not found", file=sys.stderr)
        return 1

    print(f"before: status={job.get('status')} step={job.get('step')} "
          f"§={job.get('paragraphs_done')}/{job.get('paragraphs_total')} "
          f"tasks={job.get('tasks_written')}")

    if args.full_reset:
        state.reset_for_retry(args.job_id)
        print("full reset (counters cleared; OCR reads from cache on disk)")
    else:
        state.pause(args.job_id)
        print("paused (progress counters preserved)")

    asyncio.run(enqueue_digitization(args.job_id))
    print(f"enqueued {args.job_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
