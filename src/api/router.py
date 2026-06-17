"""Content Service — API Router

Endpoints:
  POST   /api/v1/textbooks         Register a textbook + TOC (before digitization)
  POST   /api/v1/jobs              Create and enqueue a digitization job
  GET    /api/v1/jobs              List all jobs
  GET    /api/v1/jobs/{id}         Get job status + progress
  POST   /api/v1/jobs/{id}/retry   Re-enqueue a failed job
  DELETE /api/v1/jobs/{id}         Remove job from Redis (does NOT stop running job)
  GET    /api/v1/health            Health check
"""
from __future__ import annotations

import uuid
from pathlib import Path

import arq
from arq.connections import RedisSettings as ARQRedisSettings
from fastapi import APIRouter, HTTPException, status

from src.core.config import get_settings
from src.core.exceptions import JobNotFoundError
from src.core.job_state import JobStateManager, JobStatus
from src.pipeline.db_writer import DBWriter
from src.schemas.job_schemas import (
    CreateJobRequest,
    HealthResponse,
    JobCreatedResponse,
    JobListResponse,
    JobStatusResponse,
    RegisterTextbookRequest,
    RegisterTextbookResponse,
    RetryResponse,
)

router = APIRouter(prefix="/api/v1", tags=["Jobs"])

_state = JobStateManager()


# ── Textbook Registration ─────────────────────────────────────────────────────

@router.post(
    "/textbooks",
    response_model=RegisterTextbookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Зарегистрировать учебник с оглавлением перед оцифровкой",
    tags=["Textbooks"],
)
def register_textbook(body: RegisterTextbookRequest) -> RegisterTextbookResponse:
    """
    Создаёт запись учебника в БД и загружает оглавление (TOC).

    Структура TOC задаётся списком `toc`, где каждый элемент:
    - `number`       — номер раздела ("1", "3.1", "§12")
    - `title`        — заголовок ("Дроби", "Введение")
    - `level`        — уровень (1=глава, 2=параграф, 3=тема, 4=подтема)
    - `parent_number`— number родителя (для построения дерева)
    - `page_start`, `page_end` — страницы (опционально)
    - `sort_order`   — порядок (если не задан — позиция в списке)

    Возвращает `textbook_id` (UUID) для использования при создании job.
    """
    textbook_id = str(uuid.uuid4())
    writer = DBWriter()

    try:
        writer.upsert_textbook(
            textbook_id=textbook_id,
            title=body.title,
            class_level=body.class_level,
            authors=body.authors,
            subtitle=body.subtitle,
            publisher=body.publisher,
            isbn=body.isbn,
            edition=body.edition,
            total_pages=body.total_pages,
            cover_image_url=body.cover_image_url,
            subject=body.subject,
            country=body.country,
            language=body.language,
        )

        toc_count = 0
        if body.toc:
            toc_dicts = [e.model_dump() for e in body.toc]
            toc_count = writer.write_toc(textbook_id, toc_dicts)

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register textbook: {exc}",
        ) from exc

    return RegisterTextbookResponse(
        textbook_id=textbook_id,
        toc_entries=toc_count,
        message=(
            f"Textbook registered. TOC: {toc_count} entries. "
            f"Now POST /api/v1/jobs with textbook_id={textbook_id}"
        ),
    )


# ── Curriculum Setup Endpoints ────────────────────────────────────────────────

@router.post(
    "/curriculum/setup",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запустить LLM-анализ curriculum: заполнить importance + skill_prerequisites",
)
async def setup_curriculum(
    class_level: int,
    dry_run: bool = False,
) -> JobCreatedResponse:
    """
    Запускает LLM-пайплайн для одного класса:
    - Выставляет importance (1-10) для всех L2/L3/L4 узлов
    - Создаёт граф prerequisite-рёбер (hard/soft, weight, criticality)
    - Включает cross-grade зависимости из предыдущих классов

    После этого deep scan в diagnostic-service начнёт работать.

    `dry_run=true` — только логировать, не писать в БД.
    """
    if not (5 <= class_level <= 11):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="class_level must be 5–11",
        )

    job_id = str(uuid.uuid4())
    _state.create(
        job_id=job_id,
        textbook_id=f"curriculum_class_{class_level}",
        class_level=class_level,
        source_type="curriculum",
        source_path="dry_run" if dry_run else f"class_{class_level}",
    )

    pool = await arq.create_pool(_arq_redis())
    await pool.enqueue_job("run_curriculum_setup_job", job_id)
    await pool.aclose()

    return JobCreatedResponse(
        job_id=job_id,
        status="pending",
        message=(
            f"Curriculum analysis enqueued for class {class_level}"
            + (" (dry run)" if dry_run else "")
            + ". Poll /api/v1/jobs/{id} for progress."
        ),
    )


@router.get(
    "/curriculum/status/{class_level}",
    summary="Текущее состояние curriculum для класса (количество prereqs, coverage)",
)
def curriculum_status(class_level: int):
    """
    Показывает сколько prerequisite-рёбер уже есть и какой % L4-навыков
    имеют importance != 5 (дефолт).
    """
    if not (5 <= class_level <= 11):
        raise HTTPException(status_code=422, detail="class_level must be 5–11")

    try:
        from sqlalchemy import create_engine, text as sql_text
        engine = create_engine(get_settings().database_url)
        with engine.connect() as conn:
            total_l4 = conn.execute(sql_text("""
                SELECT COUNT(*) FROM knowledge_hierarchy
                WHERE level = 'L4'
                  AND class_level_start <= :cl AND class_level_end >= :cl
                  AND is_active = TRUE
            """), {"cl": class_level}).scalar()

            importance_set = conn.execute(sql_text("""
                SELECT COUNT(*) FROM knowledge_hierarchy
                WHERE level = 'L4'
                  AND class_level_start <= :cl AND class_level_end >= :cl
                  AND is_active = TRUE
                  AND importance != 5
            """), {"cl": class_level}).scalar()

            prereq_count = conn.execute(sql_text("""
                SELECT COUNT(*) FROM skill_prerequisites sp
                JOIN knowledge_hierarchy sk ON sk.id = sp.skill_id
                WHERE sk.class_level_start <= :cl AND sk.class_level_end >= :cl
            """), {"cl": class_level}).scalar()

            hard_prereq = conn.execute(sql_text("""
                SELECT COUNT(*) FROM skill_prerequisites sp
                JOIN knowledge_hierarchy sk ON sk.id = sp.skill_id
                WHERE sk.class_level_start <= :cl AND sk.class_level_end >= :cl
                  AND sp.dependency_type = 'hard'
            """), {"cl": class_level}).scalar()

        return {
            "class_level": class_level,
            "l4_skills_total": total_l4,
            "l4_importance_customized": importance_set,
            "importance_coverage_pct": round(importance_set / total_l4 * 100, 1) if total_l4 else 0,
            "prerequisites_total": prereq_count,
            "prerequisites_hard": hard_prereq,
            "deep_scan_ready": prereq_count > 0 and importance_set > 0,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _arq_redis() -> ARQRedisSettings:
    from urllib.parse import urlparse
    p = urlparse(get_settings().redis_url)
    return ARQRedisSettings(
        host=p.hostname or "localhost",
        port=p.port or 6379,
        database=int(p.path.lstrip("/") or 0),
        password=p.password,
    )


def _to_response(job: dict) -> JobStatusResponse:
    total = job.get("paragraphs_total", 0) or 0
    done = job.get("paragraphs_done", 0) or 0
    pct = round(done / total * 100, 1) if total > 0 else 0.0
    return JobStatusResponse(**{**job, "progress_pct": pct})


def _get_or_404(job_id: str) -> dict:
    job = _state.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    return job


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/jobs",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create and enqueue a digitization job",
)
async def create_job(body: CreateJobRequest) -> JobCreatedResponse:
    # Validate source file exists on disk
    if not Path(body.source_path).exists():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Source file not found: {body.source_path}",
        )

    job_id = str(uuid.uuid4())
    _state.create(
        job_id=job_id,
        textbook_id=body.textbook_id,
        class_level=body.class_level,
        source_type=body.source_type,
        source_path=body.source_path,
    )

    # Enqueue ARQ task
    pool = await arq.create_pool(_arq_redis())
    await pool.enqueue_job("run_digitization_job", job_id)
    await pool.aclose()

    return JobCreatedResponse(
        job_id=job_id,
        status="pending",
        message="Job enqueued. Poll /api/v1/jobs/{id} for progress.",
    )


@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="List all digitization jobs",
)
def list_jobs() -> JobListResponse:
    jobs = _state.list_all()
    return JobListResponse(
        jobs=[_to_response(j) for j in jobs],
        total=len(jobs),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status and progress",
)
def get_job(job_id: str) -> JobStatusResponse:
    return _to_response(_get_or_404(job_id))


@router.post(
    "/jobs/{job_id}/retry",
    response_model=RetryResponse,
    summary="Re-enqueue a failed job",
)
async def retry_job(job_id: str) -> RetryResponse:
    job = _get_or_404(job_id)

    if job.get("status") not in (JobStatus.FAILED, JobStatus.PENDING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot retry job with status '{job.get('status')}'. Only failed jobs can be retried.",
        )

    _state.reset_for_retry(job_id)

    pool = await arq.create_pool(_arq_redis())
    await pool.enqueue_job("run_digitization_job", job_id)
    await pool.aclose()

    return RetryResponse(
        job_id=job_id,
        status="pending",
        message="Job re-enqueued.",
    )


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove job record from Redis",
)
def delete_job(job_id: str) -> None:
    _get_or_404(job_id)
    import redis as _redis
    r = _redis.from_url(get_settings().redis_url)
    r.delete(f"job:{job_id}:meta")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check (legacy)",
)
def health() -> HealthResponse:
    settings = get_settings()

    # Redis ping
    try:
        import redis as _redis
        _redis.from_url(settings.redis_url).ping()
        redis_status = "ok"
    except Exception as exc:
        redis_status = f"error: {exc}"

    # DB ping
    try:
        from sqlalchemy import create_engine, text
        with create_engine(settings.database_url).connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    return HealthResponse(
        status="ok" if redis_status == "ok" and db_status == "ok" else "degraded",
        version=settings.app_version,
        redis=redis_status,
        database=db_status,
    )


@router.get("/health/live", tags=["System"], summary="Liveness probe")
def health_live():
    """Always 200 — no dependency checks."""
    return {"status": "alive"}


@router.get("/health/ready", tags=["System"], summary="Readiness probe")
def health_ready():
    """Returns 200 if DB + Redis reachable, 503 otherwise."""
    import logging
    from fastapi.responses import JSONResponse
    from sqlalchemy import create_engine, text
    import redis as _redis

    settings = get_settings()
    log = logging.getLogger(__name__)

    db_ok = True
    redis_ok = True

    try:
        with create_engine(settings.database_url).connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        log.warning("Readiness DB check failed: %s", exc)
        db_ok = False

    try:
        _redis.from_url(settings.redis_url).ping()
    except Exception as exc:
        log.warning("Readiness Redis check failed: %s", exc)
        redis_ok = False

    ready = db_ok and redis_ok
    payload = {
        "status": "ready" if ready else "not_ready",
        "version": settings.app_version,
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)
