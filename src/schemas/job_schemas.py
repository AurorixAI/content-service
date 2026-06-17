"""Content Service — Pydantic Schemas (Request / Response)"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Textbook registration ─────────────────────────────────────────────────────

class TocEntryRequest(BaseModel):
    """Одна запись оглавления учебника."""
    number: str = Field(..., description="Номер раздела: '3', '3.1', '§12'")
    title: str = Field(..., description="Заголовок: 'Дроби', 'Введение'")
    level: int = Field(..., ge=1, le=4, description="1=глава, 2=параграф, 3=тема, 4=подтема")
    parent_number: Optional[str] = Field(None, description="number родителя для построения дерева")
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    sort_order: Optional[int] = None


class RegisterTextbookRequest(BaseModel):
    """Регистрация учебника перед оцифровкой."""
    title: str = Field(..., min_length=2, description="Название учебника")
    class_level: int = Field(..., ge=5, le=11)
    authors: List[str] = Field(default_factory=list)
    subtitle: Optional[str] = None
    publisher: Optional[str] = None
    isbn: Optional[str] = None
    edition: Optional[str] = None
    total_pages: Optional[int] = None
    cover_image_url: Optional[str] = None
    subject: str = "math"
    country: str = "UZ"
    language: str = "ru"
    toc: List[TocEntryRequest] = Field(
        default_factory=list,
        description="Полное оглавление: главы, параграфы, темы"
    )


class RegisterTextbookResponse(BaseModel):
    textbook_id: str
    toc_entries: int
    message: str


# ── Job requests ──────────────────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    textbook_id: str = Field(..., description="UUID of the textbook row in the DB")
    class_level: int = Field(..., ge=5, le=11, description="Grade level 5–11")
    source_type: str = Field(default="pdf", pattern="^(pdf|json)$")
    source_path: str = Field(
        ...,
        description="Absolute path to the PDF/JSON file on the server",
        min_length=1,
    )

    @field_validator("source_path")
    @classmethod
    def path_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_path cannot be empty")
        return v.strip()


# ── Responses ─────────────────────────────────────────────────────────────────

class JobCreatedResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    id: str
    textbook_id: str
    class_level: int
    source_type: str
    source_path: str
    status: str               # pending | running | done | failed
    step: str                 # current pipeline step
    error: str
    created_at: str
    started_at: str
    finished_at: str
    paragraphs_total: int
    paragraphs_done: int
    paragraphs_failed: int = 0
    tasks_extracted: int
    tasks_written: int
    progress_pct: float       # computed: paragraphs_done / paragraphs_total * 100


class JobListResponse(BaseModel):
    jobs: list[JobStatusResponse]
    total: int


class RetryResponse(BaseModel):
    job_id: str
    status: str
    message: str


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    redis: str
    database: str
