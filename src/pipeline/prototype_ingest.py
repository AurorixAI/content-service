"""
ALGO — Приём выгрузки прототипа в контур content-service
src/pipeline/prototype_ingest.py

Прототип `newocr/mathocr` довёз 0 задач в прод, но оставил обработанный выход
по 6 книгам (2 654 задачи, 10 769 формул) — единственные реальные данные,
на которых новый контур можно прогнать целиком **без единого вызова API и без
PDF учебников**. Этот модуль переводит его записи в `ExtractedTask`.

Перевод не «копипаста полей»: у прототипа уже есть `confidence` и `needs_review`,
и это ровно словарь инварианта И1 — поэтому сигнал переносится, а не теряется.
Чего у прототипа нет — `paragraph_number`: он резал книгу постранично, без
оглавления. Поле остаётся пустым сознательно, и join ответов на таких книгах
честно отказывается работать по номеру (см. `answer_key.choose_join_strategy`),
вместо того чтобы раздать ответы наугад.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.pipeline import provenance as prov
from src.pipeline.models import ExtractedTask

#: Метки вариантов ответа: латиница A)–E). Кириллические «а) б) в)» — это
#: подпункты одной задачи, а не варианты выбора, и в options не идут.
_MCQ_LABEL = re.compile(r"^[A-E]\s*[).]?$")

#: Записи, которые не являются упражнением и в банк задач не идут.
_NON_EXERCISE_KINDS = {"definition", "theorem", "worked_example"}


def _looks_like_mcq(subtasks: List[Dict]) -> bool:
    if len(subtasks) < 2:
        return False
    return all(_MCQ_LABEL.match(str(s.get("label") or "").strip()) for s in subtasks)


def _statement_from_subtasks(subtasks: List[Dict]) -> str:
    """Собрать условие из подпунктов, когда своего условия у задачи нет.

    Формат «1. а) … б) …» — законный: весь текст лежит в подпунктах. Раньше
    они молча терялись (в `ExtractedTask` уезжали только варианты MCQ), и
    задача приезжала с пустым условием, после чего гейт её отвергал. Терялось
    185 задач из 590 на одной только `textzadachi5`.
    """
    parts = []
    for s in subtasks:
        label = str(s.get("label") or "").strip()
        md = str(s.get("md") or "").strip()
        if md:
            parts.append(f"{label} {md}".strip())
    return "\n".join(parts)


def to_task(rec: Dict[str, Any], book_id: str) -> ExtractedTask:
    """Перевести запись прототипа в `ExtractedTask` с провенансом."""
    subtasks = rec.get("subtasks") or []
    is_mcq = _looks_like_mcq(subtasks)

    statement = str(rec.get("statement_md") or "").strip()
    if not statement and subtasks and not is_mcq:
        statement = _statement_from_subtasks(subtasks)

    answer = rec.get("answer") or {}
    answer_md = str(answer.get("md") or "").strip() if isinstance(answer, dict) else ""

    task = ExtractedTask(
        temp_id=str(rec.get("task_id") or "")[:60],
        exercise_number=str(rec.get("number") or ""),
        page=int(rec.get("page") or 0),
        # Прототип резал книгу постранично, оглавления у него нет.
        paragraph_number="",
        question_text=statement,
        shared_context=str(rec.get("shared_context") or ""),
        # Формулы уже лежат внутри statement_md как $...$; дублировать их
        # в question_latex нельзя — гейты посчитали бы каждую дважды.
        question_latex="",
        answer_raw=answer_md,
        answer_type="multiple_choice" if is_mcq else "exact_number",
        answer_options=[str(s.get("md") or "") for s in subtasks] if is_mcq else None,
    )

    if answer_md:
        task.answer_source = prov.BOOK_KEY
        src_page = answer.get("source_page") if isinstance(answer, dict) else None
        task.answer_source_page = int(src_page) if isinstance(src_page, int) else None

    task.confidence = dict(rec.get("confidence") or {})
    task.text_source = prov.BOOK_OCR

    flags = list(rec.get("flags") or [])
    if rec.get("needs_review"):
        flags.append("прототип: needs_review")
    task.review_flags = [str(f) for f in flags]

    # shared_context переехал из tags в собственное поле модели (Сессия 4):
    # у него теперь есть колонка в БД и структурный слой, который его чистит
    # и распространяет на диапазон.
    task.tags = {
        "book_id": book_id,
        "kind": rec.get("kind") or "exercise",
    }
    return task


def load_book(
    book_dir: Path, *, exercises_only: bool = True
) -> Tuple[List[ExtractedTask], List[Dict]]:
    """Загрузить одну книгу: `(задачи, ответы_из_книги)`.

    `answers.json` есть не у каждой книги — раздел «Ответы» переизвлекался
    отдельной командой и до большинства книг не дошёл. Нет файла → пустой
    список, и это видно в отчёте как нулевое покрытие, а не как ошибка.
    """
    tasks_path = book_dir / "tasks.json"
    if not tasks_path.is_file():
        return [], []

    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    book_id = str(payload.get("book_id") or book_dir.name)
    records = payload.get("tasks") or []

    tasks: List[ExtractedTask] = []
    for rec in records:
        if exercises_only and (rec.get("kind") in _NON_EXERCISE_KINDS):
            continue
        tasks.append(to_task(rec, book_id))

    answers: List[Dict] = []
    answers_path = book_dir / "answers.json"
    if answers_path.is_file():
        ap = json.loads(answers_path.read_text(encoding="utf-8"))
        answers = [
            {
                "number": a.get("number"),
                "answer_md": a.get("answer_md"),
                "source_page": a.get("source_page"),
            }
            for a in (ap.get("answers") or [])
        ]

    return tasks, answers


def discover_books(root: Path) -> List[Path]:
    """Каталоги книг с выгрузкой, по алфавиту."""
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "tasks.json").is_file())
