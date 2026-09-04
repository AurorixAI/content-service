"""
ALGO — Гейты на шве записи
src/pipeline/gates.py

Здесь сходятся все проверки качества, и здесь принимается решение о судьбе
задачи: `pass` / `review` / `reject`. До этого модуля проверки существовали, но
**не стояли на пути записи**: `passes_quality_gate` смотрел только на длину
условия и непустой ответ, а формула, которая физически не рендерится, писалась
в `tasks_master` молча (задача 4 С2 не была сделана — она трогала оркестратор).

Три независимых сигнала, а не один. Замер С2 показал, почему одного мало:
на 10 769 формулах артефактов **15**, а непроходящих компиляцию — **4**.
`x \\cdot y` и `rac{1}{2}` компилируются без ошибки и показывают ученику мусор.
Компиляция и лексика ловят пересекающиеся, но разные половины класса.

Вердикт `review` — не «плохо», а «дальше решает человек». Ничего не удаляется:
задача остаётся в staging с флагами (инвариант И3).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from src.pipeline import provenance as prov
from src.pipeline.answer_key import is_empty_answer
from src.pipeline.models import ExtractedTask
from src.validate import latex_artifacts
from src.validate import katex

log = logging.getLogger("pipeline")

PASS = "pass"
REVIEW = "review"
REJECT = "reject"

#: Условие короче этого — не задача, а обрывок сегментации.
MIN_QUESTION_LEN = 12

#: Типы ответа, для которых пустой `answer_raw` допустим.
_TEXT_ANSWER_TYPES = {"text", "open_text"}

#: Формулы внутри `$...$` / `$$...$$` / `\(...\)` / `\[...\]`.
_MATH_SPANS = re.compile(
    r"\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]",
    re.DOTALL,
)


def extract_formulas(*texts: str) -> List[str]:
    """Выдрать формулы из markdown/LaTeX-текста. Пусто — формул нет."""
    out: List[str] = []
    for text in texts:
        if not text:
            continue
        for m in _MATH_SPANS.finditer(text):
            body = next((g for g in m.groups() if g is not None), "")
            body = body.strip()
            if body:
                out.append(body)
    return out


@dataclass
class Verdict:
    """Решение по одной задаче плюс причины — читаемые человеком."""

    status: str = PASS
    reasons: List[str] = field(default_factory=list)
    #: Формул проверено / из них не скомпилировалось.
    formulas_checked: int = 0
    formulas_broken: int = 0
    artifacts: List[str] = field(default_factory=list)
    #: Компиляция не запускалась (нет Node) — метрика «не измерена», а не «0».
    compile_measured: bool = True

    def add(self, status: str, reason: str) -> None:
        """Понизить вердикт до `status` (reject > review > pass) и записать причину."""
        self.reasons.append(reason)
        if status == REJECT or self.status == REJECT:
            self.status = REJECT
        elif status == REVIEW:
            self.status = REVIEW

    @property
    def ok(self) -> bool:
        return self.status == PASS

    def as_dict(self) -> Dict:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "formulas_checked": self.formulas_checked,
            "formulas_broken": self.formulas_broken,
            "artifacts": list(self.artifacts),
            "compile_measured": self.compile_measured,
        }


# ---------------------------------------------------------------------------
# Отдельные проверки
# ---------------------------------------------------------------------------


def check_structure(task: ExtractedTask, v: Verdict) -> None:
    """Задача ли это вообще. Отказ здесь — `reject`: чинить нечего.

    Это `quality.passes_quality_gate`, разложенный на причины: раньше он
    возвращал `bool`, и почему задача отброшена, узнать было нельзя.
    """
    q = (task.question_text or "").strip()
    # B1: пустое условие при непустых подпунктах — законный формат учебника
    # («1. а) … б) …»), а не дефект. На textzadachi5 это 185 задач из 590:
    # отвергать их означает выбросить треть книги с полноценным содержанием.
    has_subparts = bool(task.answer_options)
    if not q and not has_subparts:
        v.add(REJECT, "пустое условие")
        return
    if q and len(q) < MIN_QUESTION_LEN and not has_subparts:
        v.add(REJECT, f"условие короче {MIN_QUESTION_LEN} символов — обрывок сегментации")

    if task.answer_type in _TEXT_ANSWER_TYPES:
        return
    if is_empty_answer(task.answer_raw):
        v.add(REVIEW, "нет ответа при типе, который его требует")


def check_provenance(task: ExtractedTask, v: Verdict) -> None:
    """Откуда взялся ответ. Придуманный моделью — не основание для промоушена.

    Инвариант И2 в форме гейта: `ai_solved` проходит в `tasks_master` только
    через человека. Это не запрет на генерацию — это запрет выдавать её
    за напечатанное в книге.
    """
    if task.answer_source in prov.NEEDS_HUMAN and not is_empty_answer(task.answer_raw):
        v.add(REVIEW, f"ответ из источника `{task.answer_source}` — нужна проверка человеком")


def check_artifacts(task: ExtractedTask, v: Verdict) -> None:
    """Лексические артефакты LaTeX — половина класса, невидимая компиляции."""
    for text in (task.question_latex, task.question_text, task.answer_raw):
        found = latex_artifacts.find_artifacts(text or "")
        if found:
            v.artifacts.extend(found)
    if v.artifacts:
        v.add(REVIEW, f"артефакты LaTeX: {', '.join(sorted(set(v.artifacts))[:3])}")


# ---------------------------------------------------------------------------
# Батч
# ---------------------------------------------------------------------------


def check_duplicate_ids(tasks: Sequence[ExtractedTask], verdicts: Sequence[Verdict]) -> int:
    """Две задачи с одним `temp_id` — дефект сегментации, а не мелочь.

    Одинаковый идентификатор означает, что разбиение сочло два разных
    упражнения одним и тем же местом в книге. Замерено 2026-08-28 на выгрузке
    прототипа: usmanov2 — 11 таких пар, bogomolov — 4. Раньше они просто
    исчезали на записи (конфликт по ключу), и разницу между «2 603 задачи
    на входе» и «2 592 в базе» надо было заметить глазом.
    """
    seen: Dict[str, int] = {}
    flagged = 0
    for i, task in enumerate(tasks):
        tid = (task.temp_id or "").strip()
        if not tid:
            continue
        if tid in seen:
            for idx in (seen[tid], i):
                if "дубль идентификатора" not in " ".join(verdicts[idx].reasons):
                    verdicts[idx].add(REVIEW, f"дубль идентификатора `{tid}` — сегментация склеила разные задачи")
                    flagged += 1
        else:
            seen[tid] = i
    return flagged


def evaluate_batch(
    tasks: Sequence[ExtractedTask], *, compile_formulas: bool = True
) -> List[Verdict]:
    """Вердикты для батча. KaTeX зовётся один раз на весь батч, не на задачу.

    Батчинг обязателен: KaTeX — процесс Node, и запуск на каждую задачу съел бы
    больше, чем сама проверка. Нет Node → компиляция помечается «не измерена»,
    остальные гейты работают, сборка не падает.
    """
    verdicts = [Verdict() for _ in tasks]

    for task, v in zip(tasks, verdicts):
        check_structure(task, v)
        check_provenance(task, v)
        check_artifacts(task, v)

    check_duplicate_ids(tasks, verdicts)

    if not compile_formulas:
        for v in verdicts:
            v.compile_measured = False
        return verdicts

    # Собрать все формулы батча в один вызов, запомнив, чьи они.
    flat: List[str] = []
    owner: List[int] = []
    for i, task in enumerate(tasks):
        for f in extract_formulas(task.question_latex, task.question_text):
            flat.append(f)
            owner.append(i)

    if not flat:
        return verdicts

    try:
        results = katex.compile_with_errors(flat)
    except katex.KatexUnavailable as exc:
        log.info("KaTeX недоступен, компиляция не измерена: %s", exc)
        for v in verdicts:
            v.compile_measured = False
        return verdicts

    broken_msgs: Dict[int, List[str]] = {}
    for idx, res in zip(owner, results):
        verdicts[idx].formulas_checked += 1
        if not res.get("ok"):
            verdicts[idx].formulas_broken += 1
            broken_msgs.setdefault(idx, []).append(str(res.get("error") or "")[:80])

    for idx, msgs in broken_msgs.items():
        n = verdicts[idx].formulas_broken
        verdicts[idx].add(REVIEW, f"не компилируется формул: {n} ({msgs[0]})")

    return verdicts


def apply_verdicts(
    tasks: Sequence[ExtractedTask], verdicts: Sequence[Verdict]
) -> Dict[str, int]:
    """Дописать причины в `task.review_flags` и вернуть сводку по статусам.

    **Дописать, а не заменить (B43).** Здесь стояло присваивание, и оно
    затирало флаги, поставленные раньше по пути: `numbering_gap` от
    структурного слоя, `merged_across_pages` от склейки через разрыв страницы,
    флаги из `prototype_ingest`. Следующей же строкой `orchestrator._write_tasks`
    зовёт `scoring.score_tasks`, а тот читает `numbering_gap` именно отсюда —
    то есть сигнал повреждённой сегментации умирал ровно между двумя
    корректными по отдельности функциями, и задача с разрывом нумерации
    получала `structure = 1.0` вместо `0.5` и не попадала в очередь проверки.

    Порядок сохраняется, повторы не плодятся: причина гейта, уже стоящая во
    флагах (повторный прогон того же батча), второй раз не добавляется.
    """
    summary = {PASS: 0, REVIEW: 0, REJECT: 0}
    # strict=True: рассинхрон длин — ошибка программиста, а не повод молча
    # обрезать хвост. Обрезка означала бы, что часть задач не получила
    # причин и не попала в сводку, то есть брак исчез из учёта.
    for task, v in zip(tasks, verdicts, strict=True):
        flags = list(task.review_flags or [])
        seen = set(flags)
        for reason in v.reasons:
            if reason not in seen:
                flags.append(reason)
                seen.add(reason)
        task.review_flags = flags
        summary[v.status] = summary.get(v.status, 0) + 1
    return summary
