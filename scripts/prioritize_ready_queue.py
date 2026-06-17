#!/usr/bin/env python3
"""Keep only READY textbooks in ARQ queue; cancel deferred pending jobs.

Usage:
    docker exec content-worker python /app/scripts/prioritize_ready_queue.py
    docker exec content-worker python /app/scripts/prioritize_ready_queue.py --dry-run
"""
from __future__ import annotations

import argparse
import pickle
import sys
from urllib.parse import urlparse

sys.path.insert(0, "/app")

import redis

from src.core.config import get_settings
from src.core.job_state import JobStatus

# textbook keys with complete exercise-range tables
READY_KEYS = ["g6_local", "g7_makarychev"]
FINISHED_KEYS = {"g5_vilenkin", "g5_idum_ch1", "g5_idum_ch2"}
DEFER_KEYS = {"g6_vilenkin", "g7_algebra", *FINISHED_KEYS}

TEXTBOOK_IDS: dict[str, str] = {
    "g5_vilenkin": "184640af-64e7-47af-a974-8b8112e6ffb2",
    "g5_idum_ch1": "5630a994-061d-4c20-9863-fe049c8059fb",
    "g5_idum_ch2": "47167115-5961-4405-bb55-1bda8ce1b687",
    "g6_vilenkin": "351a95c1-5208-4ae9-8323-6d7dd5e8bb82",
    "g6_local": "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8",
    "g7_makarychev": "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f",
    "g7_algebra": "4b19752a-3d54-4538-b6a6-26ce1fbb48fd",
}

DEFER_IDS = {TEXTBOOK_IDS[k] for k in DEFER_KEYS if k in TEXTBOOK_IDS}
ID_TO_KEY = {v: k for k, v in TEXTBOOK_IDS.items()}


def _redis_client() -> redis.Redis:
    u = urlparse(get_settings().redis_url)
    return redis.Redis(
        host=u.hostname or "localhost",
        port=u.port or 6379,
        db=int((u.path or "/0").lstrip("/") or "0"),
        decode_responses=False,
    )


def _job_id_from_arq_payload(raw: bytes) -> str | None:
    try:
        data = pickle.loads(raw)
        args = data.get("a") or ()
        if args and isinstance(args[0], str):
            return args[0]
    except Exception:
        pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    r = _redis_client()
    removed = 0
    cancelled = 0

    # ARQ queue is a sorted set; values are arq job hash ids
    for arq_id in r.zrange("arq:queue", 0, -1):
        arq_id_s = arq_id.decode() if isinstance(arq_id, bytes) else arq_id
        payload = r.get(f"arq:job:{arq_id_s}")
        if not payload:
            continue
        job_id = _job_id_from_arq_payload(payload)
        if not job_id:
            continue
        meta = r.hgetall(f"job:{job_id}:meta")
        if not meta:
            continue
        tid = (meta.get(b"textbook_id") or b"").decode()
        status = (meta.get(b"status") or b"").decode()
        if tid in DEFER_IDS and status in ("pending", "JobStatus.PENDING", ""):
            print(f"  remove from queue: {job_id[:8]}… textbook={tid[:8]}…")
            if not args.dry_run:
                r.zrem("arq:queue", arq_id)
                r.delete(f"arq:job:{arq_id_s}", f"arq:retry:{arq_id_s}")
                r.hset(
                    f"job:{job_id}:meta",
                    mapping={
                        "status": JobStatus.FAILED,
                        "error": "deferred: exercise ranges incomplete",
                    },
                )
            removed += 1
            cancelled += 1

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Removed {removed} deferred job(s) from queue")
    print("\nRemaining queue (job_id → book):")
    for arq_id in r.zrange("arq:queue", 0, -1):
        arq_id_s = arq_id.decode() if isinstance(arq_id, bytes) else arq_id
        payload = r.get(f"arq:job:{arq_id_s}")
        job_id = _job_id_from_arq_payload(payload) if payload else None
        if not job_id:
            print(f"  ? {arq_id_s}")
            continue
        meta = r.hgetall(f"job:{job_id}:meta")
        tid = (meta.get(b"textbook_id") or b"").decode()
        status = (meta.get(b"status") or b"").decode()
        key = ID_TO_KEY.get(tid, tid[:8])
        in_prog = r.exists(f"arq:in-progress:{arq_id_s}")
        mark = "running" if in_prog else status
        print(f"  {key:16} {job_id[:8]}… [{mark}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
