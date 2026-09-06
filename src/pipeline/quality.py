"""Pipeline quality settings — единая точка для «макс. качество данных»."""
from __future__ import annotations

import re

from src.core.config import get_settings
from src.pipeline.deepseek_client import get_deepseek_model
from src.pipeline.models import ExtractedTask

_TEXT_ANSWER_TYPES = frozenset({
    "text", "open_text", "multiple_choice", "set", "equation_solution",
})

_COMMAND_PROMPT_RE = re.compile(
    r"^(решите|найдите|вычислите|запишите|упростите|определите|докажите|"
    r"постройте|сравните|решите систему|решите неравенство|решите уравнение|"
    r"найдите множество решений|найдите длины|найдите первый член|найдите сумму|"
    r"решите задачу)\b",
    re.I,
)

_PLACEHOLDER_Q_RE = re.compile(r"(не дано|нет условия|не указано|без условия|только ответ)", re.I)
_ANSWER_PLACEHOLDER_RE = re.compile(r"^(невозможно определить|невозможно|нет данных|нет ответа)$", re.I)


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _task_tail(question_text: str) -> str:
    q = _normalize(question_text)
    tail = q.rsplit(":", 1)[-1] if ":" in q else q
    tail = re.sub(r"^[абвгдеёжзийклмнопрстуфхцчшщa-z]\)\s*", "", tail, flags=re.I)
    tail = re.sub(r"^\(?[абвгдеёжзийклмнопрстуфхцчшщa-z]\)?\s*[:.]?\s*", "", tail, flags=re.I)
    return tail.strip().rstrip(".;,")


def _is_atomic_math_snippet(text: str) -> bool:
    s = _normalize(text)
    if not s:
        return False
    if _ANSWER_PLACEHOLDER_RE.match(s):
        return True
    if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", s):
        return True
    if re.fullmatch(r"[-+]?\d+/\d+", s):
        return True
    if re.fullmatch(r"[a-zA-Zа-яА-Я]\^\d+", s):
        return True
    return False


def _looks_like_fragment_stub(task: ExtractedTask) -> bool:
    q = _normalize(task.question_text)
    if not q:
        return True
    if _PLACEHOLDER_Q_RE.search(q):
        return True
    if not _COMMAND_PROMPT_RE.search(q):
        return False

    tail = _task_tail(q)
    ans = _normalize(task.answer_raw)
    if _is_atomic_math_snippet(tail) and len(tail) <= 12:
        return True
    if _is_atomic_math_snippet(ans) and len(ans) <= 24 and len(tail) <= 20:
        return True
    return False


def is_high_quality() -> bool:
    return get_settings().pipeline_quality.strip().lower() == "high"


def extraction_model(*, content_first: bool = False) -> str:
    """Extraction — всегда Flash (gemini-3.5-flash)."""
    return get_deepseek_model()


def enrichment_model() -> str:
    """Enrichment — всегда Flash."""
    return get_deepseek_model()


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
    if _looks_like_fragment_stub(task):
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
