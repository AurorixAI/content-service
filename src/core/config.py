"""Content Service — Configuration"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "ALGO Content Service"
    app_version: str = "1.0.0"
    app_env: str = Field(default="production", pattern="^(development|production|testing)$")
    debug: bool = False

    # Database — shared platform PostgreSQL
    database_url: str = "postgresql://algo:algo_password@localhost:5432/algo_v1"

    # Redis — job state + ARQ queue
    redis_url: str = "redis://localhost:6379"

    # AI — Vertex AI Gemini (ADC / service account JSON)
    gemini_api_key: str = ""  # unused when Vertex ADC is configured
    vertex_project_id: str = ""
    vertex_location: str = "global"
    gemini_flash_model: str = "gemini-3.5-flash"
    gemini_pro_model: str = "gemini-3.5-flash"

    # OCR — Gemini Vision (Vertex AI, ADC auth)
    # RENDER_DPI and BATCH_SIZE are tuned in GeminiVisionOCR directly

    # Pipeline tuning
    max_retries_gemini: int = 3
    pipeline_cache_dir: str = "/app/data/pipeline_cache"
    # high = умеренный thinking, quality gate (модель — Flash)
    pipeline_quality: str = "high"
    # Skip §1..N-1 on restart (0 = process all). E.g. 14 → start at §14.
    resume_from_paragraph: int = 0

    # Enrich/distractor chunk size per paragraph (0 = all at once)
    enrich_chunk_size: int = 8

    # Post-processing (AI A/B/C + empty skills) — defer until all books digitized
    skip_post_processing: bool = True

    # Gemini rate limiting (per process, sliding window)
    # Gemini 3.5 Flash has generous Flash-tier quotas (2000+ RPM)
    gemini_pro_rpm: int = 40
    gemini_flash_rpm: int = 40

    # Smart Verify: policy when LLM answer differs from textbook
    # ai_first | textbook | ai_if_sympy_confirms
    smart_verify_answer_authority: str = Field(
        default="ai_if_sympy_confirms",
        pattern="^(ai_first|textbook|ai_if_sympy_confirms)$",
    )
    smart_verify_text_authority: str = Field(
        default="textbook",
        pattern="^(ai_first|textbook|ai_if_sympy_confirms)$",
    )
    smart_verify_consistency_runs: int = 3
    smart_verify_consistency_temperature: float = 0.2
    distractor_gate_min_count: int = 3
    distractor_gate_min_acceptable: int = 2
    distractor_gate_max_retries: int = 4
    distractor_gate_llm_batch_size: int = 5

    # Figures storage (persistent docker volume → served by FastAPI static)
    figures_dir: str = "/app/data/figures"
    figures_url_prefix: str = "/api/v1/figures"

    # ARQ worker concurrency
    worker_concurrency: int = 5

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
