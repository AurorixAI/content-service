"""Pipeline quality settings — единая точка для «макс. качество данных»."""
from __future__ import annotations

from src.core.config import get_settings
from src.pipeline.gemini_client import get_flash_model
from src.pipeline.models import ExtractedTask

_TEXT_ANSWER_TYPES = frozenset({
    "text", "open_text", "multiple_choice", "set", "equation_solution",
})


def is_high_quality() -> bool:
    return get_settings().pipeline_quality.strip().lower() == "high"


def extraction_model(*, content_first: bool = False) -> str:
    """Extraction — всегда Flash (gemini-3.5-flash)."""
    return get_flash_model()


def enrichment_model() -> str:
    """Enrichment — всегда Flash."""
    return get_flash_model()


def thinking_budget(step: str) -> int:
    if not is_high_quality():
        return 0
    # Умеренный thinking: extract без thinking (1 вызов/§), enrich — основной расход
    return {
        "extraction": 0,
        "enrichment": 2048,
    }.get(step, 0)


def extraction_temperature() -> float:
    return 0.0 if is_high_quality() else 0.1


def enrichment_max_tokens() -> int:
    return 4096 if is_high_quality() else 2048


def enrichment_retry_max(*, missing_answer: bool) -> int:
    """Повтор только если нужно вычислить ответ (дороже и важнее)."""
    if not is_high_quality():
        return 1
    return 2 if missing_answer else 1


def passes_quality_gate(task: ExtractedTask) -> bool:
    """Минимальные требования перед записью в БД."""
    q = (task.question_text or "").strip()
    if len(q) < 12:
        return False
    ans = (task.answer_raw or "").strip()
    if task.answer_type in _TEXT_ANSWER_TYPES:
        # текстовые / MC — допускаем без числового ответа (LLM-grader)
        return True
    if not ans or ans in ("—", "-", "?", "...", "…"):
        return False
    return True


def filter_quality_tasks(tasks: list[ExtractedTask]) -> tuple[list[ExtractedTask], int]:
    kept = [t for t in tasks if passes_quality_gate(t)]
    return kept, len(tasks) - len(kept)
