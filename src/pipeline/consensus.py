"""
ALGO — Согласие независимых проходов (инвариант И5)
src/pipeline/consensus.py

Инвариант: **согласие — маршрутизатор внимания, а не сертификат.**

Цена не ограничение, поэтому спорную страницу можно прогнать несколько раз
(разные модели / промпты / температура) и сравнить. Но у этого приёма есть
граница, и её надо назвать вслух, иначе он превращается в самообман:

    **согласие ≠ правота.** Два прохода одной модели при temperature 0.1
    почти всегда совпадут — и совпадут в том числе на общей ошибке.

Ровно об этом предупреждает `src/eval/golden/README.md` применительно к
эталону: «эталон, полученный не ручной вычиткой, измеряет согласованность
системы с самой собой, а не качество». Здесь то же самое.

Поэтому:
* расхождение → задача уходит в ревью (сигнал сильный и дешёвый);
* согласие → **не даёт** промоушена само по себе, только снимает флаг
  расхождения; решают остальные гейты.

Второе следствие — запуск **выборочный**. Гнать N проходов по всему корпусу
бессмысленно: лишние проходы умножают самую дешёвую стадию. Запускаем их там,
где бесплатный локальный сигнал уже сказал «подозрительно» (`should_consensus`).
На выгрузке прототипа такие задачи — около 3% (86 из 2 654).
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.eval.canonical import canonicalize
from src.pipeline import gates as G
from src.pipeline import provenance as prov
from src.pipeline.answer_key import is_empty_answer
from src.pipeline.models import ExtractedTask

log = logging.getLogger("pipeline")


# ---------------------------------------------------------------------------
# Когда вообще звать второй проход
# ---------------------------------------------------------------------------


def should_consensus(
    task: ExtractedTask,
    verdict: Optional[G.Verdict] = None,
    *,
    paragraph_has_gap: bool = False,
) -> tuple[bool, List[str]]:
    """Нужен ли повторный проход. Решается **бесплатными локальными сигналами**.

    Ни один триггер ниже не стоит ни одного вызова модели — это и есть условие
    того, чтобы выборочный консенсус оставался дешёвым.
    """
    reasons: List[str] = []

    if verdict is not None:
        if verdict.artifacts:
            reasons.append("артефакты LaTeX в извлечении")
        if verdict.formulas_broken:
            reasons.append(f"не компилируется формул: {verdict.formulas_broken}")

    if not (task.question_text or "").strip():
        reasons.append("пустое условие")
    if paragraph_has_gap:
        reasons.append("дыра в нумерации параграфа")
    if task.answer_source == prov.AI_SOLVED:
        reasons.append("ответ придуман моделью")
    if task.answer_type not in ("text", "open_text") and is_empty_answer(task.answer_raw):
        reasons.append("нет ответа")

    return bool(reasons), reasons


def gapped_paragraphs(tasks: Sequence[ExtractedTask]) -> set[str]:
    """Параграфы с пропусками в нумерации упражнений.

    Единственный сигнал, ловящий ошибки сегментации: задача, потерянная при
    разбиении страницы, не оставляет никакого следа, кроме дыры в номерах.
    """
    from src.eval.metrics import missing_numbers

    rows = [
        {"number": t.exercise_number, "paragraph": t.paragraph_number}
        for t in tasks
    ]
    return set(missing_numbers(rows).keys())


# ---------------------------------------------------------------------------
# Сравнение проходов
# ---------------------------------------------------------------------------


@dataclass
class ConsensusResult:
    """Итог сравнения нескольких независимых проходов."""

    n_passes: int = 0
    #: Наиболее частый вариант в канонизованном виде (не для записи в БД).
    majority: Optional[str] = None
    #: Сколько проходов дали большинство.
    majority_count: int = 0
    unanimous: bool = False
    variants: Dict[str, int] = field(default_factory=dict)

    @property
    def agreement(self) -> Optional[float]:
        """Доля проходов, сошедшихся на большинстве. None — сравнивать нечего."""
        if not self.n_passes:
            return None
        return round(self.majority_count / self.n_passes, 4)

    @property
    def disagreed(self) -> bool:
        return self.n_passes > 1 and not self.unanimous

    def as_dict(self) -> Dict[str, Any]:
        return {
            "n_passes": self.n_passes,
            "agreement": self.agreement,
            "unanimous": self.unanimous,
            "majority_count": self.majority_count,
            "variants": dict(self.variants),
        }


def compare_passes(
    outputs: Sequence[str], *, normalize: Callable[[str], str] = canonicalize
) -> ConsensusResult:
    """Сравнить выходы проходов по канонизованному виду.

    Канонизация обязательна: `\\dfrac` и `\\frac`, лишние пробелы и
    `\\left(`/`(` — это одно и то же содержание, и считать их расхождением
    значит утопить настоящие расхождения в шуме форматирования.
    """
    normed = [normalize(o or "") for o in outputs]
    normed = [n for n in normed if n]
    if not normed:
        # Сравнивать нечего: n_passes=0, чтобы `agreement` вернул None.
        # Вернуть здесь len(outputs) значило бы отчитаться «согласие 0%»
        # там, где согласие просто не измерялось.
        return ConsensusResult()

    counts = Counter(normed)
    majority, majority_count = counts.most_common(1)[0]
    return ConsensusResult(
        n_passes=len(normed),
        majority=majority,
        majority_count=majority_count,
        unanimous=len(counts) == 1,
        variants=dict(counts),
    )


def route(
    task: ExtractedTask, verdict: G.Verdict, result: ConsensusResult
) -> G.Verdict:
    """Применить итог консенсуса к вердикту — **только маршрутизацией**.

    Расхождение понижает до `review`. Согласие НЕ повышает до `pass`: это
    прямое требование инварианта И5. Если задача уже была в `review` по другой
    причине, единогласие её оттуда не вытащит.
    """
    if result.disagreed:
        pct = int((result.agreement or 0) * 100)
        verdict.add(
            G.REVIEW,
            f"проходы разошлись: согласие {pct}% из {result.n_passes}",
        )
    else:
        # Отмечаем факт, но статус не трогаем — согласие не сертификат.
        task.confidence = dict(task.confidence or {})
        task.confidence["consensus"] = result.agreement
    return verdict
