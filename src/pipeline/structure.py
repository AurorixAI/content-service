"""
ALGO — Структурный слой (Сессия 4)
src/pipeline/structure.py

Три детерминированные постобработки извлечённого потока задач. Все три —
эвристики без ML и без вызовов модели: они работают с уже полученным текстом.

1. **shared_context** — «В задачах 140–145 решите уравнение:» относится к
   шести задачам, а напечатано один раз. Без него запись бессмысленна:
   ученик видит «а) x² − 9 = 0» без указания, что с этим делать.
2. **merge** — задача, разорванная переносом страницы, приходит двумя
   обрывками: хвост первой страницы без завершающей пунктуации и фрагмент
   без номера в начале следующей.
3. **ordering** — двухколоночная вёрстка заставляет читать по колонкам
   (1, 4, 2, 5, 3, 6), и порядок записей не совпадает с номерами.

Отличие от прототипа `mathocr`, откуда перенесена логика: там раздел
угадывался по сбросу номера на 1, потому что другого признака не было.
Здесь есть настоящий `paragraph_number` из оглавления — группируем по нему,
и границы разделов перестают быть догадкой.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Sequence, Tuple

from src.eval.metrics import int_prefix
from src.pipeline import scoring as _scoring
from src.pipeline.models import ExtractedTask

log = logging.getLogger("pipeline")

# ── 1. Общий контекст группы задач ─────────────────────────────────────────

#: Императивы — признак настоящей вводной-инструкции, а не заголовка темы.
_IMPERATIVES = (
    "решите", "решить", "упростите", "упростить", "вычислите", "вычислить",
    "найдите", "найти", "докажите", "доказать", "сократите", "сократить",
    "постройте", "построить", "определите", "определить", "разложите",
    "преобразуйте", "составьте", "запишите", "выполните", "сравните",
    "укажите", "приведите", "представьте",
)
#: Узбекские аналоги — часть корпуса на узбекском (country=UZ).
_IMPERATIVES_UZ = (
    "hisoblang", "toping", "soddalashtiring", "yeching", "isbotlang",
    "keltiring", "yozing",
)

#: «В задачах 140–145 …», «В задании 12 …», «Задачи 3—7 …».
_RANGE_RE = re.compile(
    r"(?:задач(?:ах|и|е)?|задани(?:ях|и|е)?|упражнени(?:ях|и|е)?)"
    r"\D{0,6}?(\d+)\s*[–—-]\s*(\d+)",
    re.IGNORECASE,
)


def parse_range(text: str) -> Tuple[int, int] | None:
    """Диапазон номеров из вводной: «В задачах 140–145» → (140, 145)."""
    m = _RANGE_RE.search(text or "")
    if not m:
        return None
    lo, hi = int(m.group(1)), int(m.group(2))
    return (lo, hi) if lo <= hi else (hi, lo)


def is_shared_instruction(text: str) -> bool:
    """Вводная-инструкция, а не заголовок раздела.

    Заголовок темы («Алгебраические выражения») — короткое именное
    словосочетание без глагола и без диапазона: он не говорит, что делать,
    и в `shared_context` попал по ошибке извлечения.
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    if parse_range(low):
        return True
    return any(w in low for w in _IMPERATIVES) or any(w in low for w in _IMPERATIVES_UZ)


def _by_paragraph(tasks: Sequence[ExtractedTask]) -> Dict[str, List[ExtractedTask]]:
    """Сгруппировать по параграфу, сохраняя порядок внутри группы."""
    groups: Dict[str, List[ExtractedTask]] = {}
    for t in tasks:
        groups.setdefault(str(t.paragraph_number or ""), []).append(t)
    return groups


def apply_shared_context(tasks: Sequence[ExtractedTask]) -> Dict[str, int]:
    """Снять ложные вводные и распространить диапазонные. Мутирует задачи.

    Возвращает {cleaned, propagated}.
    """
    cleaned = 0
    for t in tasks:
        sc = (t.shared_context or "").strip()
        if sc and not is_shared_instruction(sc):
            t.shared_context = ""
            cleaned += 1

    propagated = 0
    for group in _by_paragraph(tasks).values():
        for src in group:
            sc = (src.shared_context or "").strip()
            if not sc:
                continue
            rng = parse_range(sc)
            if not rng:
                continue
            lo, hi = rng
            for t in group:
                n = int_prefix(t.exercise_number)
                if n is not None and lo <= n <= hi and not (t.shared_context or "").strip():
                    t.shared_context = sc
                    propagated += 1
    return {"cleaned": cleaned, "propagated": propagated}


# ── 2. Склейка через разрыв страницы ───────────────────────────────────────

#: Завершающая пунктуация. Двоеточие — НЕ финал: после него ждём продолжения.
_TERMINAL = tuple(".!?)]}»\"'")
#: Явный номер в начале («12.», «12)») — это новая задача, не хвост.
_NUMBER_START = re.compile(r"^\s*\d+\s*[.)]")


def _ends_unfinished(text: str) -> bool:
    """Условие оборвано: не заканчивается терминальной пунктуацией."""
    t = (text or "").rstrip()
    return bool(t) and not t.endswith(_TERMINAL)


def _is_continuation(task: ExtractedTask) -> bool:
    """Похоже на хвост-продолжение: нет собственного номера."""
    if str(task.exercise_number or "").strip():
        return False
    stmt = (task.question_text or "").strip()
    return bool(stmt) and not _NUMBER_START.match(stmt)


def merge_page_breaks(tasks: Sequence[ExtractedTask]) -> Tuple[List[ExtractedTask], int]:
    """Слить хвосты-продолжения в предыдущую оборванную задачу.

    Условия склейки (все обязательны):
    * предыдущая задача обрывается без терминальной пунктуации;
    * текущая — фрагмент без номера;
    * они на одной странице или на соседних (перенос через разрыв);
    * они в одном параграфе — через границу параграфа не склеиваем.
    """
    if not tasks:
        return [], 0

    result: List[ExtractedTask] = [tasks[0]]
    merged = 0
    for cur in tasks[1:]:
        prev = result[-1]
        same_para = str(prev.paragraph_number or "") == str(cur.paragraph_number or "")
        near_page = int(cur.page or 0) in (int(prev.page or 0), int(prev.page or 0) + 1)
        if (
            same_para
            and near_page
            and _is_continuation(cur)
            and _ends_unfinished(prev.question_text)
        ):
            prev.question_text = f"{(prev.question_text or '').strip()} {(cur.question_text or '').strip()}".strip()
            if cur.question_latex and not prev.question_latex:
                prev.question_latex = cur.question_latex
            for fid in cur.figure_refs or []:
                if fid not in prev.figure_refs:
                    prev.figure_refs.append(fid)
            if cur.requires_figure:
                prev.requires_figure = True
            if "merged_across_pages" not in prev.review_flags:
                prev.review_flags.append("merged_across_pages")
            merged += 1
            continue
        result.append(cur)
    return result, merged


# ── 3. Порядок внутри параграфа ────────────────────────────────────────────

_SUFFIX_RE = re.compile(r"^\d+(.*)$")


def _sort_key(task: ExtractedTask) -> tuple:
    """«142а» → (142, 'а'), «1.5» → (1, '.5'). Устойчиво к буквенным подпунктам."""
    num = str(task.exercise_number or "").strip()
    n = int_prefix(num)
    m = _SUFFIX_RE.match(num)
    suffix = m.group(1) if m else num
    return (n if n is not None else 10**9, suffix)


def order_within_paragraphs(
    tasks: Sequence[ExtractedTask],
) -> Tuple[List[ExtractedTask], int]:
    """Отсортировать по номеру внутри параграфа, не пересекая его границы.

    Пробег прерывается сменой параграфа или задачей без номера: безномерная
    задача — жёсткий якорь и остаётся на своём месте, иначе сортировка
    растащила бы вводные и врезки.
    """
    result: List[ExtractedTask] = []
    run: List[ExtractedTask] = []
    reordered = 0

    def flush() -> None:
        nonlocal reordered
        if not run:
            return
        ordered = sorted(run, key=_sort_key)
        if [id(t) for t in ordered] != [id(t) for t in run]:
            reordered += 1
        result.extend(ordered)
        run.clear()

    current_para: str | None = None
    for t in tasks:
        para = str(t.paragraph_number or "")
        if int_prefix(t.exercise_number) is None:
            flush()
            result.append(t)
            current_para = None
            continue
        if current_para is not None and para != current_para:
            flush()
        current_para = para
        run.append(t)
    flush()
    return result, reordered


# ── 4. Разрывы нумерации ───────────────────────────────────────────────────

#: Флаг разрыва нумерации. Определение живёт в `scoring` — там он и
#: потребляется (`score_structure`, `needs_review`). Своя копия строки здесь
#: разошлась бы с потребителем молча, а молчаливое расхождение — ровно то,
#: из-за чего эта ветка и была мертва.
NUMBERING_GAP_FLAG = _scoring.NUMBERING_GAP_FLAG


def flag_numbering_gaps(tasks: Sequence[ExtractedTask]) -> int:
    """Пометить задачи, за которыми в параграфе пропущен номер. Мутирует задачи.

    Вторая половина B43. `scoring.score_structure` понижает доверие по флагу
    `numbering_gap`, а `needs_review` отправляет такую задачу в очередь — но
    флаг не выставлял **никто**: одноимённая метрика в `src/eval/metrics.py`
    считает пропуски по дампу постфактум и в задачу ничего не пишет. Ветка
    была мертва и по затиранию флагов (`gates.apply_verdicts`), и по
    отсутствию производителя; чинить надо оба конца, иначе сигнал остаётся
    мёртвым.

    Место выбрано по единственному подходящему условию: считать разрывы можно
    только на ПОЛНОМ списке задач параграфа. `_write_tasks` получает чанки,
    и чанк рвёт параграф посередине — там любой разрыв был бы выдуманным.
    Структурный слой, наоборот, гарантированно видит параграф целиком
    (`orchestrator._apply_structure`).

    Помечается не весь параграф, а задача **перед** дырой: она и есть место,
    где сегментация вероятнее всего проглотила соседнюю. Пометить всю группу
    значило бы отправить в очередь параграф целиком из-за одного пропуска.

    Пропуски считаются по множеству номеров в диапазоне [min..max], поэтому
    двухколоночная вёрстка (1, 4, 2, 5, 3, 6) ложных разрывов не даёт, а
    границы параграфа не считаются дырами: чего нет за краем, того не видно.
    """
    flagged = 0
    for group in _by_paragraph(tasks).values():
        present = {n for n in (int_prefix(t.exercise_number) for t in group) if n is not None}
        if len(present) < 2:
            continue
        top = max(present)
        for task in group:
            n = int_prefix(task.exercise_number)
            # Дыра справа от задачи — и при этом не за краем параграфа.
            if n is None or n >= top or (n + 1) in present:
                continue
            if NUMBERING_GAP_FLAG in (task.review_flags or []):
                continue
            task.review_flags = list(task.review_flags or []) + [NUMBERING_GAP_FLAG]
            flagged += 1
    return flagged


# ── Сборка ─────────────────────────────────────────────────────────────────

def apply(tasks: Sequence[ExtractedTask]) -> Tuple[List[ExtractedTask], Dict[str, int]]:
    """Прогнать весь структурный слой. Возвращает (задачи, сводка).

    Порядок фиксирован и важен: склейка работает с потоком в том виде, в каком
    его прочитала модель, поэтому сортировка идёт ПОСЛЕ неё — иначе хвост и его
    голова разъедутся до склейки и обрывок останется обрывком.

    Разрывы нумерации считаются ПОСЛЕДНИМИ: до склейки хвост без номера ещё
    не приклеен к голове, и часть «пропусков» была бы следствием разрыва
    страницы, а не потери задачи.
    """
    empty = {"cleaned": 0, "propagated": 0, "merged": 0, "reordered": 0, "numbering_gaps": 0}
    if not tasks:
        return [], empty

    sc = apply_shared_context(tasks)
    merged_tasks, merged = merge_page_breaks(tasks)
    ordered_tasks, reordered = order_within_paragraphs(merged_tasks)
    gaps = flag_numbering_gaps(ordered_tasks)

    summary = {
        "cleaned": sc["cleaned"],
        "propagated": sc["propagated"],
        "merged": merged,
        "reordered": reordered,
        "numbering_gaps": gaps,
    }
    return ordered_tasks, summary
