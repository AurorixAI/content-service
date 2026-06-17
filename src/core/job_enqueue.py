"""Digitization job helpers — direct ARQ enqueue (manual book-by-book workflow)."""
from __future__ import annotations

import logging
from typing import Optional

import arq
import redis

from src.core.config import get_settings
from src.core.job_state import JobStateManager, JobStatus

log = logging.getLogger(__name__)

LEGACY_QUEUE_KEY = "digitization:sequential_queue"


def _redis_bytes() -> redis.Redis:
    return redis.from_url(get_settings().redis_url, decode_responses=False)


def _arq_settings():
    from urllib.parse import urlparse

    u = urlparse(get_settings().redis_url)
    return arq.connections.RedisSettings(
        host=u.hostname or "localhost",
        port=u.port or 6379,
        database=int((u.path or "/0").lstrip("/") or "0"),
    )


def clear_legacy_sequential_queue() -> int:
    """Remove deprecated Redis sequential queue list."""
    r = redis.from_url(get_settings().redis_url, decode_responses=True)
    n = r.llen(LEGACY_QUEUE_KEY)
    if n:
        r.delete(LEGACY_QUEUE_KEY)
        log.info("Cleared legacy sequential queue (%d job(s))", n)
    return n


def clear_arq_digitization_queue() -> int:
    """Remove pending digitization jobs from ARQ (keep in-progress)."""
    r = _redis_bytes()
    removed = 0
    for arq_id in r.zrange("arq:queue", 0, -1):
        arq_id_s = arq_id.decode() if isinstance(arq_id, bytes) else arq_id
        if r.exists(f"arq:in-progress:{arq_id_s}"):
            continue
        payload = r.get(f"arq:job:{arq_id_s}")
        if payload and b"run_digitization_job" in payload:
            r.zrem("arq:queue", arq_id)
            r.delete(f"arq:job:{arq_id_s}", f"arq:retry:{arq_id_s}")
            removed += 1
        elif not payload:
            r.zrem("arq:queue", arq_id)
            removed += 1
    return removed


def reset_zombie_running() -> list[str]:
    """Reset jobs stuck as running without an active ARQ in-progress marker."""
    r = _redis_bytes()
    in_progress_job_ids: set[str] = set()
    import pickle

    for key in r.scan_iter("arq:in-progress:*"):
        key_s = key.decode() if isinstance(key, bytes) else key
        arq_id = key_s.split(":")[-1]
        payload = r.get(f"arq:job:{arq_id}")
        if not payload:
            continue
        try:
            data = pickle.loads(payload)
            args = data.get("a") or ()
            if args:
                in_progress_job_ids.add(str(args[0]))
        except Exception:
            pass

    reset: list[str] = []
    state = JobStateManager()
    r_text = redis.from_url(get_settings().redis_url, decode_responses=True)
    for key in r_text.scan_iter("job:*:meta"):
        data = r_text.hgetall(key)
        if data.get("status") not in (JobStatus.RUNNING, "running"):
            continue
        jid = key.replace("job:", "").replace(":meta", "")
        if jid in in_progress_job_ids:
            continue
        state.reset_for_retry(jid)
        reset.append(jid)
        log.warning("Reset zombie running job: %s", jid)
    return reset


async def enqueue_digitization(job_id: str) -> str:
    """Enqueue a digitization job directly in ARQ."""
    pool = await arq.create_pool(_arq_settings())
    try:
        await pool.enqueue_job("run_digitization_job", job_id)
        log.info("Enqueued digitization job %s", job_id)
        return job_id
    finally:
        await pool.aclose()


async def startup_cleanup() -> Optional[str]:
    """Worker startup: clear legacy queue, reset zombies. Does not auto-enqueue."""
    clear_legacy_sequential_queue()
    reset = reset_zombie_running()
    if reset:
        log.info("Startup: reset %d zombie job(s): %s", len(reset), reset)
    return None
