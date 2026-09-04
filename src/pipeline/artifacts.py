"""
ALGO — Артефакты стадий, адресуемые по хэшу входа (инвариант И4)
src/pipeline/artifacts.py

Инвариант: **каждая стадия оставляет артефакт, ключ которого — хэш входа,
версии стадии и промпта.**

Швы уже были: `PipelineStep.{OCR, LEGEND, SPLIT, EXTRACT, VALIDATE, ENRICH,
DISTRACTORS, CLASSIFY, WRITE}` в `src/core/job_state.py`. Но состояние жило
в Redis (TTL), а выход шёл сразу в БД, и промежуточного результата не
оставалось нигде.

Смысл не в экономии вызовов — цена не ограничение. Смысл в **воспроизводимости
и диффуемости**: поменял промпт извлечения, перегнал только извлечение, сравнил
2 654 задачи до и после, увидел ровно что изменилось. Без этого любое улучшение
промпта — вера, а не измерение.

Ключ включает версию стадии и текст промпта осознанно: правка промпта обязана
инвалидировать кэш, иначе «улучшение» тихо вернёт старый результат — самый
неприятный вид ложного успеха.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

log = logging.getLogger("pipeline")

#: Версия формата самого артефакта. Меняется, если меняется схема записи.
ARTIFACT_FORMAT = 1


def _canonical_bytes(payload: Any) -> bytes:
    """Стабильная сериализация входа: порядок ключей фиксирован."""
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def stage_key(
    stage: str, payload: Any, *, version: str = "1", prompt: Optional[str] = None
) -> str:
    """Ключ артефакта: sha256(стадия + версия + промпт + вход).

    Промпт входит в ключ — см. докстринг модуля. Если стадия не использует
    промпт (сегментация, склейка), передавайте `None`.
    """
    h = hashlib.sha256()
    h.update(stage.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(version).encode("utf-8"))
    h.update(b"\x00")
    h.update((prompt or "").encode("utf-8"))
    h.update(b"\x00")
    h.update(_canonical_bytes(payload))
    return h.hexdigest()


@dataclass
class Artifact:
    """Сохранённый выход одной стадии."""

    key: str
    stage: str
    value: Any
    meta: Dict[str, Any]

    @property
    def created_at(self) -> Optional[float]:
        return self.meta.get("created_at")


class ArtifactStore:
    """Файловое хранилище артефактов, адресуемое содержимым.

    Файлы, а не Redis: артефакт должен пережить перезапуск и TTL — иначе
    сравнение «до/после» невозможно ровно тогда, когда оно нужнее всего.
    """

    def __init__(self, root: Optional[str | Path] = None):
        if root is None:
            try:
                from src.core.config import get_settings
                root = Path(get_settings().pipeline_cache_dir) / "stages"
            except Exception:
                root = Path("data/pipeline_cache/stages")
        self.root = Path(root)

    def _path(self, stage: str, key: str) -> Path:
        # Шардим по первым двум символам: каталог на десятки тысяч файлов
        # тормозит на любой ФС.
        return self.root / stage / key[:2] / f"{key}.json"

    def get(self, stage: str, key: str) -> Optional[Artifact]:
        p = self._path(stage, key)
        if not p.is_file():
            return None
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("артефакт %s нечитаем, игнорирую: %s", p, exc)
            return None
        return Artifact(key=key, stage=stage, value=raw.get("value"), meta=raw.get("meta", {}))

    def put(
        self, stage: str, key: str, value: Any, meta: Optional[Dict[str, Any]] = None
    ) -> Artifact:
        p = self._path(stage, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        full_meta = {"created_at": time.time(), "format": ARTIFACT_FORMAT, **(meta or {})}
        blob = json.dumps(
            {"value": value, "meta": full_meta}, ensure_ascii=False, default=str
        )
        # Атомарная запись: частично записанный артефакт хуже отсутствующего —
        # его прочитают как валидный кэш.
        tmp = p.with_suffix(".tmp")
        tmp.write_text(blob, encoding="utf-8")
        os.replace(tmp, p)
        return Artifact(key=key, stage=stage, value=value, meta=full_meta)

    def cached(
        self,
        stage: str,
        payload: Any,
        compute: Callable[[], Any],
        *,
        version: str = "1",
        prompt: Optional[str] = None,
        force: bool = False,
    ) -> tuple[Any, bool]:
        """Вернуть `(значение, из_кэша)`; посчитать и сохранить, если нет.

        `force=True` пересчитывает, игнорируя кэш, но результат перезаписывает —
        так «перегнать заново» не создаёт второй истины.
        """
        key = stage_key(stage, payload, version=version, prompt=prompt)
        if not force:
            hit = self.get(stage, key)
            if hit is not None:
                return hit.value, True
        value = compute()
        self.put(stage, key, value, meta={"version": version})
        return value, False

    # ── Диффуемость ──────────────────────────────────────────────────────

    def diff_keys(self, stage: str) -> list[str]:
        """Все ключи стадии — вход для сравнения двух прогонов."""
        base = self.root / stage
        if not base.is_dir():
            return []
        return sorted(p.stem for p in base.glob("*/*.json"))
