"""
ALGO — Доверие и очередь ручной проверки (Сессия 5)
src/pipeline/scoring.py

Гейты (`gates.py`) отвечают на вопрос «пускать ли задачу дальше» — да/нет/через
человека. Этот модуль отвечает на другой: **насколько мы в ней уверены и кого
человеку проверять первым.** Вердикт дискретен, доверие — непрерывно, и очередь
строится именно по нему.

Считается из уже готового вердикта, а не заново: KaTeX прогоняется один раз на
батч в `gates.evaluate_batch`, и вторая компиляция тех же формул стоила бы
столько же, сколько первая, ничего не добавив.

**Исправление B1.** В прототипе `structure = 0.0` ставился при пустом условии, и
у 185 из 590 задач `textzadachi5` это срабатывало ложно: условие там пусто
законно — весь текст лежит в подпунктах («1. а) … б) …»). Прогон как есть
отправил бы 31% книги в ручную проверку без причины. Штрафуем, только если
пусто И условие, И подпункты.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

from src.core.config import get_settings
from src.pipeline import gates as G
from src.pipeline import provenance as prov
from src.pipeline.models import ExtractedTask

log = logging.getLogger("pipeline")

#: Маркер, которым извлечение помечает нечитаемый фрагмент вместо догадки.
UNREADABLE = "[unreadable]"
#: Потолок `ocr` при нечитаемом фрагменте: сколько бы формул ни скомпилировалось,
#: дыра в тексте важнее.
_UNREADABLE_CAP = 0.30
#: `structure` при разрыве нумерации — единственный сигнал на ошибку сегментации.
_GAP_STRUCTURE = 0.50
#: Флаг разрыва нумерации, как его ставит структурный/валидирующий слой.
NUMBERING_GAP_FLAG = "numbering_gap"


def _task_text(task: ExtractedTask) -> str:
    return " ".join(
        str(x or "")
        for x in (task.question_text, task.shared_context, task.question_latex, task.answer_raw)
    )


def _has_subparts(task: ExtractedTask) -> bool:
    """Есть ли у задачи подпункты, несущие содержание.

    Ядро исправления B1: `answer_options` — это и есть «а) … б) …» из книги.
    """
    return bool(task.answer_options)


def score_ocr(task: ExtractedTask, v: G.Verdict) -> Optional[float]:
    """Уверенность в распознавании: компиляция формул + маркер нечитаемого.

    `None` — не измерено (нет Node и нет других сигналов), а не «плохо».
    """
    measured: Optional[float] = None
    if v.compile_measured and v.formulas_checked:
        measured = (v.formulas_checked - v.formulas_broken) / v.formulas_checked

    if v.artifacts:
        # Артефакты компиляция не видит: `x \\cdot y` рендерится молча.
        penalty = min(0.5, 0.1 * len(set(v.artifacts)))
        measured = (1.0 if measured is None else measured) - penalty

    if UNREADABLE in _task_text(task):
        measured = min(_UNREADABLE_CAP, 1.0 if measured is None else measured)

    return None if measured is None else round(max(0.0, min(1.0, measured)), 4)


def score_structure(task: ExtractedTask) -> float:
    """Уверенность в структуре: есть ли содержание и цела ли нумерация."""
    has_statement = bool((task.question_text or "").strip())
    # B1: пусто условие, но есть подпункты — законный формат, не дефект.
    if not has_statement and not _has_subparts(task):
        return 0.0
    if NUMBERING_GAP_FLAG in (task.review_flags or []):
        return _GAP_STRUCTURE
    if not has_statement:
        # Содержание есть, но не там, где ожидалось: не брак, но и не идеал.
        return 0.75
    return 1.0


def score_answer(task: ExtractedTask) -> Optional[float]:
    """Уверенность в ответе — производная от его источника, не от его вида.

    Напечатанный в книге ответ и придуманный моделью выглядят одинаково;
    различает их только провенанс (И1).
    """
    src = task.answer_source
    if src == prov.ABSENT:
        return None
    return {
        prov.BOOK_KEY: 1.0,
        prov.BOOK_SOLUTION: 0.95,
        prov.SYMPY_DERIVED: 0.80,
        prov.AI_SOLVED: 0.40,
    }.get(src, 0.40)


def awaiting_answer(task: ExtractedTask) -> bool:
    """У задачи нет ответа из книги — вопрос полноты, а не качества.

    Такие задачи и так не пройдут промоушен (`gate_status` у них не `pass`),
    поэтому в `tasks_master` ничего не просочится. Смешивать их с браком
    распознавания нельзя: на выгрузке прототипа это 2 496 задач из 2 603, и
    очередь, куда попало 97% книги, не очередь — в ней нечего приоритизировать.
    """
    return task.answer_source in prov.NEEDS_HUMAN


def needs_review(task: ExtractedTask, v: G.Verdict, conf: prov.Confidence) -> bool:
    """Нужна ли ручная проверка КАЧЕСТВА. Вычисляется, вручную не проставляется.

    Сюда попадает только то, что система считает **испорченным**: битая формула,
    лексический артефакт, структурное повреждение, разрыв нумерации, жёсткий
    отказ гейта. Отсутствие ответа сюда НЕ входит — см. `awaiting_answer`.

    Это разделение — не смягчение гейта. Гейт остаётся единственным условием
    промоушена и по-прежнему держит `review`/`reject` вне `tasks_master`.
    Здесь решается другой вопрос: кого человеку смотреть первым.
    """
    s = get_settings()
    if v.status == G.REJECT:
        return True
    if v.formulas_broken > 0 or v.artifacts:
        return True
    if conf.ocr is not None and conf.ocr < s.ocr_confidence_threshold:
        return True
    if conf.structure is not None and conf.structure < s.structure_confidence_threshold:
        return True
    return NUMBERING_GAP_FLAG in (task.review_flags or [])


def review_priority(task: ExtractedTask, conf: prov.Confidence) -> float:
    """Ключ очереди ручной проверки: чем меньше, тем раньше смотреть.

    Минимум по измеренным компонентам — узкое место задачи. Неизмеренное не
    притворяется нулём и не лезет в начало очереди вперёд реального брака.
    """
    worst = conf.min_measured()
    return 1.0 if worst is None else worst


def score_tasks(
    tasks: Sequence[ExtractedTask], verdicts: Sequence[G.Verdict]
) -> Dict[str, object]:
    """Проставить `confidence` и `review_flags` на месте. Вернуть сводку."""
    assert len(tasks) == len(verdicts), "вердикт нужен на каждую задачу"

    n_review = 0
    n_awaiting = 0
    measured_ocr: List[float] = []
    for task, v in zip(tasks, verdicts, strict=True):
        conf = prov.Confidence(
            ocr=score_ocr(task, v),
            structure=score_structure(task),
            answer=score_answer(task),
        )
        task.confidence = conf.as_dict()
        if conf.ocr is not None:
            measured_ocr.append(conf.ocr)

        if needs_review(task, v, conf):
            n_review += 1
            if "needs_review" not in task.review_flags:
                task.review_flags.append("needs_review")
        if awaiting_answer(task):
            n_awaiting += 1

    return {
        "n_tasks": len(tasks),
        "n_needs_review": n_review,
        "n_awaiting_answer": n_awaiting,
        "review_rate": round(n_review / len(tasks), 4) if tasks else 0.0,
        "ocr_measured": len(measured_ocr),
        "ocr_mean": round(sum(measured_ocr) / len(measured_ocr), 4) if measured_ocr else None,
    }


def review_queue(
    tasks: Sequence[ExtractedTask], verdicts: Sequence[G.Verdict]
) -> List[ExtractedTask]:
    """Задачи, требующие проверки, в порядке «сначала худшее»."""
    flagged = [
        # strict=True — иначе при рассинхроне длин часть задач молча не
        # попадёт в очередь проверки, а это ровно та потеря, которую
        # очередь и должна предотвращать.
        t for t, v in zip(tasks, verdicts, strict=True)
        if needs_review(t, v, prov.Confidence.from_dict(t.confidence))
    ]
    return sorted(
        flagged,
        key=lambda t: review_priority(t, prov.Confidence.from_dict(t.confidence)),
    )
