#!/usr/bin/env python3
"""Clear stale worker state (legacy sequential queue, zombie jobs, pending ARQ).

Usage:
    docker exec content-worker python /app/scripts/clear_worker_state.py
    docker exec content-worker python /app/scripts/clear_worker_state.py --dry-run
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "/app")

from src.core.job_enqueue import (
    clear_arq_digitization_queue,
    clear_legacy_sequential_queue,
    reset_zombie_running,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        print("[DRY-RUN] Would clear legacy queue, pending ARQ digitization jobs, reset zombies")
        return 0

    legacy = clear_legacy_sequential_queue()
    removed = clear_arq_digitization_queue()
    reset = reset_zombie_running()
    print(f"Legacy sequential queue: {legacy} job(s) removed")
    print(f"Pending ARQ digitization jobs: {removed} removed")
    print(f"Zombie jobs reset: {len(reset)}")
    if reset:
        for jid in reset:
            print(f"  {jid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
