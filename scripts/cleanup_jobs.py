#!/usr/bin/env python3
"""Cancel stale jobs and flush ARQ queue before a clean restart.

Usage:
    docker exec content-worker python /app/scripts/cleanup_jobs.py
    docker exec content-worker python /app/scripts/cleanup_jobs.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse

sys.path.insert(0, "/app")

import redis

from src.core.config import get_settings
from src.core.job_state import JobStatus


def _redis_client() -> redis.Redis:
    u = urlparse(get_settings().redis_url)
    return redis.Redis(
        host=u.hostname or "localhost",
        port=u.port or 6379,
        db=int((u.path or "/0").lstrip("/") or "0"),
        decode_responses=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    r = _redis_client()
    cancelled = 0
    deleted = 0

    for key in r.scan_iter("job:*:meta"):
        data = r.hgetall(key)
        st = data.get("status", "")
        if st in (JobStatus.RUNNING, "running", JobStatus.PENDING, "pending"):
            jid = key.replace("job:", "").replace(":meta", "")
            print(f"  cancel job {jid[:8]}… status={st}")
            if not args.dry_run:
                r.hset(key, mapping={
                    "status": JobStatus.FAILED,
                    "error": "cancelled by cleanup_jobs.py",
                })
            cancelled += 1

    arq_patterns = ("arq:queue", "arq:job:*", "arq:retry:*", "arq:in-progress:*")
    for pattern in arq_patterns:
        for key in r.scan_iter(pattern):
            print(f"  del {key}")
            if not args.dry_run:
                r.delete(key)
            deleted += 1

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Cancelled {cancelled} jobs, deleted {deleted} ARQ keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
