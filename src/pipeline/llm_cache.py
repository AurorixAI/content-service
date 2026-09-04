"""
ALGO — Кэш ответов модели
src/pipeline/llm_cache.py

Один SQLite-файл рядом с кэшем OCR. Ключ — хэш от модели, промпта и параметров
генерации; значение — сырой текст ответа.

**Кэшируются только успешные ответы.** Это не мелочь, а условие корректности:
в `distractors._ai_generate_distractors` повтор после сбоя идёт с **тем же
промптом** (список отклонённых ещё пуст). Если бы в кэш попадал отказ, ретрай
после 429 доставал бы из кэша тот же отказ и никогда не пробивался. Ошибка в
кэш не кладётся — повтор честно идёт в сеть.

Зачем вообще: генерация дистракторов — самая дорогая стадия конвейера, и она
не кэшировалась вовсе. На первом живом прогоне книги именно на ней кончились
предоплаченные кредиты, а любой перепрогон оплачивал бы её заново.

Отключается `LLM_CACHE_ENABLED=false` — на случай, когда нужна свежая
генерация (например, при отладке промпта; правка самого промпта меняет ключ
и инвалидирует кэш сама).
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.config import get_settings

log = logging.getLogger("pipeline")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_cache (
    key        TEXT PRIMARY KEY,
    model      TEXT NOT NULL,
    response   TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def enabled() -> bool:
    """Кэш включён? Выключается переменной окружения."""
    return os.getenv("LLM_CACHE_ENABLED", "true").strip().lower() not in (
        "false", "0", "no", "off",
    )


class LLMCache:
    """Потокобезопасный кэш ответов модели поверх SQLite."""

    def __init__(self, path: Optional[Path] = None) -> None:
        if path is None:
            path = Path(get_settings().pipeline_cache_dir) / "llm_cache.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        # check_same_thread=False: конвейер ходит в модель из нескольких
        # потоков, а запись сериализуется своим замком.
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    @staticmethod
    def make_key(model: str, prompt: str, **params: Any) -> str:
        """Ключ по модели, промпту и параметрам генерации.

        Параметры входят в ключ намеренно: ответ при `temperature=0.0` и
        `temperature=0.4` — разные ответы, и подменять один другим нельзя.
        """
        parts = [model, prompt]
        for name in sorted(params):
            parts.append(f"{name}={params[name]!r}")
        return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT response FROM llm_cache WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def set(self, key: str, model: str, response: str) -> None:
        """Положить УСПЕШНЫЙ ответ. Пустой ответ не кэшируется."""
        if not response:
            return
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, model, response) VALUES (?, ?, ?)",
                (key, model, response),
            )
            self._conn.commit()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            n = self._conn.execute("SELECT count(*) FROM llm_cache").fetchone()[0]
        return {"entries": n, "path": str(self.path)}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_CACHE: Optional[LLMCache] = None
_CACHE_LOCK = threading.Lock()


#: Кэш уже пытались открыть и не смогли. Повторять на каждый вызов незачем.
_CACHE_DISABLED = False


def get_cache() -> Optional[LLMCache]:
    """Общий кэш процесса. `None`, если выключен или недоступен.

    Недоступность кэша не должна ронять обращение к модели: кэш — ускорение,
    а не часть контракта. Проверено фактом: дефолт `pipeline_cache_dir`
    указывает на `/app/data/pipeline_cache` (путь внутри контейнера), и при
    запуске того же кода на хосте SQLite падал на read-only `/app`, унося с
    собой каждый вызов Gemini. Теперь такой запуск просто идёт без кэша.
    """
    global _CACHE, _CACHE_DISABLED
    if not enabled() or _CACHE_DISABLED:
        return None
    if _CACHE is None:
        with _CACHE_LOCK:
            if _CACHE is None and not _CACHE_DISABLED:
                try:
                    _CACHE = LLMCache()
                except (OSError, sqlite3.Error) as exc:
                    _CACHE_DISABLED = True
                    log.warning(
                        "LLM-кэш недоступен (%s) — работаем без него", str(exc)[:120],
                    )
                    return None
                log.info("LLM-кэш: %s", _CACHE.stats())
    return _CACHE
