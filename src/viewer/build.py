"""
ALGO — Вьюер очереди ручной проверки (Сессия 5)
src/viewer/build.py

Один статический HTML: карточки задач в порядке «сначала худшее», формулы
рендерит KaTeX, не отрендерилось — красная рамка. Фильтр «только требующие
проверки». Никакого SPA и React — файл открывается двойным кликом.

Отличие от вьюера прототипа: там слева был скан страницы, здесь его нет —
content-service держит задачи в БД, а не рядом с рендерами страниц. Вместо
скана карточка показывает то, чего у прототипа не было: вердикт гейтов
с причинами и провенанс ответа. Проверяющему важнее знать, **почему** задача
в очереди, чем видеть страницу, которую он и так откроет в книге.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from src.pipeline import gates as G
from src.pipeline import provenance as prov
from src.pipeline import scoring as SC
from src.pipeline.models import ExtractedTask

log = logging.getLogger("pipeline")

_TEMPLATE = Path(__file__).parent / "template.html"

#: Человекочитаемые подписи источников ответа.
_SOURCE_LABEL = {
    prov.BOOK_KEY: "ответ из книги",
    prov.BOOK_SOLUTION: "из решения в книге",
    prov.SYMPY_DERIVED: "выведен SymPy",
    prov.AI_SOLVED: "придуман моделью",
    prov.ABSENT: "ответа нет",
}


def _esc(text: object) -> str:
    """HTML-эскейп с сохранением `$…$`, чтобы KaTeX увидел формулу."""
    return html.escape(str(text or ""), quote=False)


def _fmt(value: Optional[float]) -> str:
    """`None` — «не измерено», а не «0.00». Дисциплина из provenance.Confidence."""
    return "—" if value is None else f"{value:.2f}"


def _card(task: ExtractedTask, verdict: G.Verdict) -> str:
    conf = prov.Confidence.from_dict(task.confidence)
    flagged = SC.needs_review(task, verdict, conf)
    cls = "reject" if verdict.status == G.REJECT else ("review" if flagged else "")

    badges: List[str] = []
    if verdict.status == G.REJECT:
        badges.append('<span class="badge rej">reject</span>')
    elif flagged:
        badges.append('<span class="badge rev">на проверку</span>')
    badges.append(
        f'<span class="badge conf">ocr {_fmt(conf.ocr)} · '
        f'стр {_fmt(conf.structure)} · отв {_fmt(conf.answer)}</span>'
    )
    src_cls = "src ai" if task.answer_source in prov.NEEDS_HUMAN else "src"
    badges.append(
        f'<span class="badge {src_cls}">'
        f'{_esc(_SOURCE_LABEL.get(task.answer_source, task.answer_source))}</span>'
    )

    parts = [f'<div class="card {cls}">']
    para = f"§{_esc(task.paragraph_number)} " if task.paragraph_number else ""
    parts.append(
        f'<div class="chead"><span class="num">{para}№{_esc(task.exercise_number)}</span>'
        f'<span class="kind">стр. {_esc(task.page)}</span>{"".join(badges)}</div>'
    )
    if (task.shared_context or "").strip():
        parts.append(f'<div class="shared">{_esc(task.shared_context)}</div>')
    parts.append(f"<div>{_esc(task.question_text)}</div>")
    if task.answer_options:
        items = "".join(f"<li>{_esc(o)}</li>" for o in task.answer_options)
        parts.append(f'<ul class="subs">{items}</ul>')
    if (task.answer_raw or "").strip():
        page = (
            f' <span class="asrc">(стр. {task.answer_source_page})</span>'
            if task.answer_source_page else ""
        )
        parts.append(f'<div class="answer">Ответ: {_esc(task.answer_raw)}{page}</div>')
    if verdict.reasons:
        spans = "".join(f"<span>{_esc(r)}</span>" for r in verdict.reasons)
        parts.append(f'<div class="reasons">{spans}</div>')
    parts.append("</div>")
    return "\n".join(parts)


def build_html(
    tasks: Sequence[ExtractedTask],
    verdicts: Sequence[G.Verdict],
    *,
    title: str = "Очередь ручной проверки",
) -> str:
    """Собрать HTML целиком. Порядок карточек — очередь проверки."""
    assert len(tasks) == len(verdicts), "вердикт нужен на каждую задачу"

    pairs = list(zip(tasks, verdicts))
    # Сначала худшее: то, что требует проверки, вверху и отсортировано по
    # минимальной измеренной уверенности.
    pairs.sort(
        key=lambda tv: (
            0 if SC.needs_review(tv[0], tv[1], prov.Confidence.from_dict(tv[0].confidence)) else 1,
            SC.review_priority(tv[0], prov.Confidence.from_dict(tv[0].confidence)),
        )
    )

    n_review = sum(
        1 for t, v in pairs
        if SC.needs_review(t, v, prov.Confidence.from_dict(t.confidence))
    )
    stats = (
        f"задач: {len(pairs)} · на проверку: {n_review}"
        f" ({n_review / len(pairs):.1%})" if pairs else "задач: 0"
    )

    content = "\n".join(_card(t, v) for t, v in pairs)
    tpl = _TEMPLATE.read_text(encoding="utf-8")
    return (
        tpl.replace("__TITLE__", _esc(title))
        .replace("__STATS__", _esc(stats))
        .replace("__CONTENT__", content)
    )


def build_viewer(
    tasks: Sequence[ExtractedTask],
    verdicts: Sequence[G.Verdict],
    out_path: Path | str,
    *,
    title: str = "Очередь ручной проверки",
) -> Path:
    """Записать вьюер на диск. Возвращает путь к файлу."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_html(tasks, verdicts, title=title), encoding="utf-8")
    log.info("вьюер: %d задач → %s", len(tasks), path)
    return path
