"""Content Service — Job State Manager (Redis)

Job state schema (stored as Redis Hash):
  job:{id}:meta   → {id, textbook_id, class_level, status, step, error,
                      created_at, started_at, finished_at,
                      paragraphs_total, paragraphs_done,
                      tasks_extracted, tasks_written}

Status transitions:
  pending → running → done
                    → failed
  failed  → pending  (via retry)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import redis

from src.core.config import get_settings

log = logging.getLogger(__name__)

# Redis key TTL: 30 days
JOB_TTL_SECONDS = 60 * 60 * 24 * 30


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class PipelineStep(str, Enum):
    OCR = "ocr"
    LEGEND = "legend"
    SPLIT = "split"
    EXTRACT = "extract"
    VALIDATE = "validate"
    ENRICH = "enrich"
    DISTRACTORS = "distractors"
    CLASSIFY = "classify"
    WRITE = "write"
    COMPLETE = "complete"


def _redis() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)


def _key(job_id: str) -> str:
    return f"job:{job_id}:meta"


class JobStateManager:
    """CRUD for digitization job state in Redis."""

    def __init__(self) -> None:
        self._r = _redis()

    # ── Create ────────────────────────────────────────────────────────────

    def create(
        self,
        job_id: str,
        textbook_id: str,
        class_level: int,
        source_type: str,  # "pdf" | "json"
        source_path: str,
        *,
        content_first: bool = False,
        target_paragraphs: list[str] | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        meta = {
            "id": job_id,
            "textbook_id": textbook_id,
            "class_level": class_level,
            "source_type": source_type,
            "source_path": source_path,
            "content_first": "1" if content_first else "0",
            "target_paragraphs": json.dumps(target_paragraphs or []),
            "status": JobStatus.PENDING,
            "step": "",
            "error": "",
            "created_at": now,
            "started_at": "",
            "finished_at": "",
            "paragraphs_total": 0,
            "paragraphs_done": 0,
            "paragraphs_failed": 0,
            "tasks_extracted": 0,
            "tasks_written": 0,
        }
        k = _key(job_id)
        self._r.hset(k, mapping={kk: str(v) for kk, v in meta.items()})
        self._r.expire(k, JOB_TTL_SECONDS)
        log.info("Job created: %s (textbook=%s)", job_id, textbook_id)
        return meta

    # ── Read ──────────────────────────────────────────────────────────────

    def get(self, job_id: str) -> Optional[dict]:
        data = self._r.hgetall(_key(job_id))
        if not data:
            return None
        # Coerce numeric fields
        for field in ("class_level", "paragraphs_total", "paragraphs_done",
                      "paragraphs_failed", "tasks_extracted", "tasks_written"):
            if field in data:
                try:
                    data[field] = int(data[field])
                except (ValueError, TypeError):
                    data[field] = 0
        data["content_first"] = str(data.get("content_first", "0")) == "1"
        raw_targets = data.get("target_paragraphs") or "[]"
        try:
            data["target_paragraphs"] = json.loads(raw_targets)
        except (json.JSONDecodeError, TypeError):
            data["target_paragraphs"] = []
        return data

    def list_all(self) -> list[dict]:
        """Return all jobs, sorted by created_at desc."""
        keys = self._r.keys("job:*:meta")
        jobs = []
        pipe = self._r.pipeline()
        for k in keys:
            pipe.hgetall(k)
        results = pipe.execute()
        for data in results:
            if not data:
                continue
            for field in ("class_level", "paragraphs_total", "paragraphs_done",
                          "paragraphs_failed", "tasks_extracted", "tasks_written"):
                try:
                    data[field] = int(data.get(field, 0))
                except (ValueError, TypeError):
                    data[field] = 0
            jobs.append(data)
        return sorted(jobs, key=lambda x: x.get("created_at", ""), reverse=True)

    # ── Update ────────────────────────────────────────────────────────────

    def start(self, job_id: str, step: PipelineStep) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._r.hset(_key(job_id), mapping={
            "status": JobStatus.RUNNING,
            "step": step,
            "started_at": now,
            "error": "",
        })
        self._r.expire(_key(job_id), JOB_TTL_SECONDS)

    def set_step(self, job_id: str, step: PipelineStep) -> None:
        self._r.hset(_key(job_id), "step", step)

    def set_paragraphs_total(self, job_id: str, total: int) -> None:
        self._r.hset(_key(job_id), "paragraphs_total", total)

    def increment_paragraph(self, job_id: str, tasks_extracted: int) -> None:
        pipe = self._r.pipeline()
        pipe.hincrby(_key(job_id), "paragraphs_done", 1)
        pipe.hincrby(_key(job_id), "tasks_extracted", tasks_extracted)
        pipe.execute()

    def increment_paragraph_failed(self, job_id: str) -> None:
        self._r.hincrby(_key(job_id), "paragraphs_failed", 1)

    def increment_written(self, job_id: str, count: int) -> None:
        self._r.hincrby(_key(job_id), "tasks_written", count)

    def complete(self, job_id: str, tasks_written: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._r.hset(_key(job_id), mapping={
            "status": JobStatus.DONE,
            "step": PipelineStep.COMPLETE,
            "finished_at": now,
            "tasks_written": tasks_written,
            "error": "",
        })
        self._r.expire(_key(job_id), JOB_TTL_SECONDS)
        log.info("Job completed: %s, written=%d", job_id, tasks_written)

    def fail(self, job_id: str, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._r.hset(_key(job_id), mapping={
            "status": JobStatus.FAILED,
            "finished_at": now,
            "error": error[:1000],
        })
        self._r.expire(_key(job_id), JOB_TTL_SECONDS)
        log.error("Job failed: %s — %s", job_id, error)

    def reset_for_retry(self, job_id: str) -> None:
        """Reset failed job back to pending so worker picks it up again."""
        self._r.hset(_key(job_id), mapping={
            "status": JobStatus.PENDING,
            "step": "",
            "error": "",
            "started_at": "",
            "finished_at": "",
            "paragraphs_done": 0,
            "paragraphs_failed": 0,
            "tasks_extracted": 0,
            "tasks_written": 0,
        })
        self._r.expire(_key(job_id), JOB_TTL_SECONDS)
        log.info("Job reset for retry: %s", job_id)

    def pause(self, job_id: str) -> None:
        """Mark running job as pending without clearing progress (for sequential queue)."""
        self._r.hset(_key(job_id), mapping={
            "status": JobStatus.PENDING,
            "step": "",
            "error": "",
            "started_at": "",
        })
        self._r.expire(_key(job_id), JOB_TTL_SECONDS)
        log.info("Job paused: %s", job_id)
