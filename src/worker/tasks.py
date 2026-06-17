"""Content Service — ARQ Worker

ARQ (async Redis Queue) task: runs the full digitization pipeline
for a single job. Called by ARQ worker process.

Each task:
  1. Marks job as running in Redis
  2. Instantiates DigitizationOrchestrator
  3. Runs the pipeline (PDF or JSON)
  4. Marks job done / failed

Worker settings are at the bottom of this file (used by `arq worker`).
"""
from __future__ import annotations

import logging
import traceback

from src.core.config import get_settings
from src.core.exceptions import PipelineError
from src.core.job_state import JobStateManager, JobStatus, PipelineStep
from src.pipeline.orchestrator import DigitizationOrchestrator
from src.pipeline.curriculum_setup import CurriculumSetupOrchestrator

# Ensure INFO logs from the pipeline modules show up under ARQ
# (ARQ inherits root logger which defaults to WARNING).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("src.pipeline").setLevel(logging.INFO)

log = logging.getLogger(__name__)


async def run_digitization_job(ctx: dict, job_id: str) -> dict:
    """
    ARQ task entry point.

    Args:
        ctx: ARQ context (contains redis pool, etc.)
        job_id: job identifier in Redis

    Returns:
        {"status": "done" | "failed", "tasks_written": int}
    """
    state = JobStateManager()

    job = state.get(job_id)
    if not job:
        log.error("Job %s not found in Redis", job_id)
        return {"status": "error", "tasks_written": 0}

    if job.get("status") == JobStatus.DONE:
        log.warning("Job %s already completed (done), skipping duplicate run", job_id)
        return {"status": "already_done", "tasks_written": int(job.get("tasks_written", 0))}

    if job.get("status") == JobStatus.RUNNING:
        log.warning("Job %s already running, skipping duplicate", job_id)
        return {"status": "already_running", "tasks_written": 0}

    state.start(job_id, PipelineStep.OCR)
    log.info("Worker picked up job %s (textbook=%s, class=%s)",
             job_id, job["textbook_id"], job["class_level"])

    tasks_written = 0
    orchestrator = DigitizationOrchestrator(
        job_id=job_id,
        textbook_id=job["textbook_id"],
        class_level=int(job["class_level"]),
        content_first=bool(job.get("content_first")),
        target_paragraphs=(
            {str(p) for p in job.get("target_paragraphs", [])}
            if job.get("target_paragraphs")
            else None
        ),
    )
    try:
        source_type = job.get("source_type", "pdf")
        source_path = job["source_path"]

        if source_type == "json":
            tasks_written = orchestrator.run_json(source_path)
        else:
            tasks_written = orchestrator.run_pdf(source_path)

        state.complete(job_id, tasks_written)
        log.info("Job %s done — %d tasks written", job_id, tasks_written)

        settings = get_settings()
        if settings.skip_post_processing:
            log.info(
                "Post-processing skipped (skip_post_processing=true) — "
                "run manually after all books are digitized"
            )
        else:
            # ── Post-processing: fill gaps in A/B/C coverage and distractors ──
            try:
                from src.pipeline.post_processing import run_post_processing

                pp_result = run_post_processing(
                    db_url=settings.database_url,
                    class_level=int(job["class_level"]),
                )
                log.info(
                    "Post-processing: +%d tasks, %d distractors filled",
                    pp_result["new_tasks"],
                    pp_result["distractors_filled"],
                )
            except Exception as pp_exc:
                log.warning("Post-processing failed (non-critical): %s", pp_exc)

        return {"status": "done", "tasks_written": tasks_written}

    except PipelineError as exc:
        err = str(exc)
        log.error("Job %s pipeline error: %s", job_id, err)
        state.fail(job_id, err)
        orchestrator.writer.update_digitization_status(job["textbook_id"], "error")
        return {"status": "failed", "tasks_written": tasks_written}

    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-800:]}"
        log.error("Job %s unexpected error: %s", job_id, err)
        state.fail(job_id, err)
        orchestrator.writer.update_digitization_status(
            job["textbook_id"], "error", tasks_extracted=tasks_written
        )
        return {"status": "failed", "tasks_written": tasks_written, "error": str(exc)}


async def run_curriculum_setup_job(ctx: dict, job_id: str) -> dict:
    """
    ARQ task: LLM-анализ curriculum для одного class_level.
    Заполняет importance + skill_prerequisites.
    """
    state = JobStateManager()

    job = state.get(job_id)
    if not job:
        log.error("Curriculum job %s not found", job_id)
        return {"status": "error"}

    if job.get("status") == JobStatus.RUNNING:
        return {"status": "already_running"}

    state.start(job_id, PipelineStep.CLASSIFY)
    class_level = int(job.get("class_level", 5))
    dry_run = job.get("source_path", "") == "dry_run"

    log.info("Curriculum setup job %s: class=%d dry_run=%s", job_id, class_level, dry_run)

    try:
        orchestrator = CurriculumSetupOrchestrator(
            job_id=job_id,
            class_level=class_level,
            dry_run=dry_run,
        )
        result = orchestrator.run()
        state.complete(job_id, result["prerequisites_inserted"])
        log.info("Curriculum job %s done: %s", job_id, result)
        return {"status": "done", **result}

    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        log.error("Curriculum job %s failed: %s", job_id, err)
        state.fail(job_id, err)
        return {"status": "failed", "error": err}


# ── ARQ WorkerSettings ────────────────────────────────────────────────────────

def _build_redis_settings():
    """Build ARQ RedisSettings from REDIS_URL env var."""
    from arq.connections import RedisSettings as ARQRedisSettings
    from urllib.parse import urlparse
    url = get_settings().redis_url
    p = urlparse(url)
    return ARQRedisSettings(
        host=p.hostname or "localhost",
        port=p.port or 6379,
        database=int(p.path.lstrip("/") or 0),
        password=p.password,
    )


class WorkerSettings:
    """Configuration consumed by `arq worker src.worker.tasks.WorkerSettings`."""

    functions = [run_digitization_job, run_curriculum_setup_job]
    redis_settings = _build_redis_settings()
    max_jobs = 1          # one textbook at a time — avoids Gemini 429/timeouts
    job_timeout = 14400   # 4 hours max per job (large textbooks)
    keep_result = 86400   # keep result in Redis for 24 h

    @staticmethod
    async def on_startup(ctx: dict) -> None:
        from src.core.job_enqueue import startup_cleanup

        await startup_cleanup()
