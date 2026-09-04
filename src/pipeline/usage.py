"""
ALGO — Учёт расхода токенов
src/pipeline/usage.py

До этого модуля стоимость прогона можно было только оценивать: ответы модели
сохранялись без `usageMetadata`, и на вопрос «сколько стоила книга» ответа не
было. Разбор в `prod.md` так и начинался с оговорки «точных usage-цифр в
проекте нет». Первый живой прогон это подтвердил на практике: предоплаченные
кредиты кончились на 95% книги, и сказать, сколько именно ушло, нечем.

Счётчик процессный и потокобезопасный. Записи в БД нет намеренно: расход —
свойство прогона, а не задачи, и его место в логе и в отчёте, а не в строке
`tasks_staging`.

Цены не зашиты: они меняются и зависят от тарифа. Модуль считает **токены**,
а деньги считает тот, кто знает тариф — `estimate_cost` принимает цены явно.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

log = logging.getLogger("pipeline")


@dataclass
class ModelUsage:
    """Расход по одной модели."""

    calls: int = 0
    cached_calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens + self.thinking_tokens

    def as_dict(self) -> Dict[str, int]:
        return {
            "calls": self.calls,
            "cached_calls": self.cached_calls,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "thinking_tokens": self.thinking_tokens,
            "total_tokens": self.total_tokens,
        }


class UsageTracker:
    """Накопитель расхода за прогон. Потокобезопасен."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_model: Dict[str, ModelUsage] = {}

    def record(self, model: str, usage_metadata: Optional[Dict[str, Any]]) -> None:
        """Учесть один ответ модели.

        `usageMetadata` может не прийти (старый ответ, ошибка формата) — тогда
        считаем вызов, но не токены. Занулять токены нельзя: «не измерено» и
        «ноль» — разные вещи, та же дисциплина, что в `provenance.Confidence`.
        """
        md = usage_metadata or {}
        with self._lock:
            u = self._by_model.setdefault(model, ModelUsage())
            u.calls += 1
            u.prompt_tokens += int(md.get("promptTokenCount") or 0)
            u.output_tokens += int(md.get("candidatesTokenCount") or 0)
            u.thinking_tokens += int(md.get("thoughtsTokenCount") or 0)

    def record_cache_hit(self, model: str) -> None:
        """Вызов, который обслужен кэшем и не стоил ничего."""
        with self._lock:
            self._by_model.setdefault(model, ModelUsage()).cached_calls += 1

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            return {m: u.as_dict() for m, u in self._by_model.items()}

    def totals(self) -> ModelUsage:
        total = ModelUsage()
        with self._lock:
            for u in self._by_model.values():
                total.calls += u.calls
                total.cached_calls += u.cached_calls
                total.prompt_tokens += u.prompt_tokens
                total.output_tokens += u.output_tokens
                total.thinking_tokens += u.thinking_tokens
        return total

    def reset(self) -> None:
        with self._lock:
            self._by_model.clear()

    def format_report(self) -> str:
        """Человекочитаемая сводка для лога в конце прогона."""
        snap = self.snapshot()
        if not snap:
            return "расход: вызовов не было"
        lines = ["расход по моделям:"]
        for model, u in sorted(snap.items()):
            lines.append(
                f"  {model}: вызовов {u['calls']} (из кэша {u['cached_calls']}) · "
                f"вход {u['prompt_tokens']} · выход {u['output_tokens']} · "
                f"размышление {u['thinking_tokens']} · всего {u['total_tokens']}"
            )
        t = self.totals()
        lines.append(
            f"  ИТОГО: вызовов {t.calls} (из кэша {t.cached_calls}) · "
            f"токенов {t.total_tokens}"
        )
        return "\n".join(lines)


def estimate_cost(
    usage: ModelUsage, *, input_per_1m: float, output_per_1m: float
) -> float:
    """Стоимость в долларах по явно переданному тарифу.

    Цены параметром, а не константой: тарифы меняются, различаются между
    моделями и режимами (Batch API дешевле вдвое), и зашитая в код цифра
    протухла бы молча. Токены «размышления» тарифицируются как выход.
    """
    inp = usage.prompt_tokens / 1_000_000 * input_per_1m
    out = (usage.output_tokens + usage.thinking_tokens) / 1_000_000 * output_per_1m
    return round(inp + out, 6)


#: Общий счётчик процесса.
TRACKER = UsageTracker()
