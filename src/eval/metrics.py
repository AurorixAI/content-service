"""Метрики качества оцифровки.

- `task_recall`         — доля golden-задач, найденных в банке;
- `latex_ned`           — нормализованный edit distance по канонизованному LaTeX;
- `numbering_gaps`      — пропуски в нумерации упражнений внутри параграфа;
- `formula_compile_rate`— доля компилирующихся формул (KaTeX → Сессия 2, пока None);
- `answer_join_coverage`— доля ответов из книги, а не от ИИ (Сессия 3, пока None).

BLEU не используется.

**Все функции здесь чистые** — принимают списки словарей, в БД не ходят.
Доступ к `tasks_master` живёт в `scripts/eval.py`. Так метрики покрываются
юнит-тестами без поднятого PostgreSQL.

Форма записи задачи (нормализованная, см. `scripts/eval.py:fetch_tasks`):

    {"id": "G8_12_142", "paragraph": "12", "number": "142",
     "question_text": "...", "question_latex": "...", "correct_answer": "...",
     "answer_source": None}
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Iterable

from src.eval.canonical import canonicalize, extract_formulas, extract_formulas_raw

GOLDEN_DIR = Path(__file__).parent / "golden"

_INT_PREFIX = re.compile(r"\d+")


# ── загрузка golden ────────────────────────────────────────────────────────
def golden_path(name: str) -> Path:
    return GOLDEN_DIR / f"{name}.jsonl"


def load_golden(name: str) -> list[dict]:
    """Прочитать golden-набор. Строки-комментарии (`#`) и пустые — пропускаются."""
    path = golden_path(name)
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(json.loads(line))
    return out


# ── вспомогательное ────────────────────────────────────────────────────────
def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _ned(a: str, b: str) -> float:
    return _levenshtein(a, b) / max(len(a), len(b), 1)


def int_prefix(number: object) -> int | None:
    """Целочисленный префикс номера: `142а` → 142, `1.5` → 1, `A` → None."""
    m = _INT_PREFIX.match(str(number or "").strip())
    return int(m.group()) if m else None


def _key(task: dict) -> tuple[str, str]:
    """Ключ совпадения — (параграф, номер).

    Одного номера недостаточно: нумерация упражнений сбрасывается в каждом
    параграфе, номер 142 встречается многократно.
    """
    return (str(task.get("paragraph", "")).strip(), str(task.get("number", "")).strip())


def _task_text(task: dict) -> str:
    """Весь текст задачи, где могут быть формулы."""
    return " ".join(
        str(task.get(f) or "")
        for f in ("question_latex", "question_text", "correct_answer")
    )


# ── метрики ────────────────────────────────────────────────────────────────
def task_recall(golden: list[dict], tasks: list[dict]) -> float | None:
    """Доля golden-задач, найденных в банке (матч по параграф+номер)."""
    if not golden:
        return None
    keys = {_key(t) for t in tasks}
    found = sum(1 for g in golden if _key(g) in keys)
    return round(found / len(golden), 4)


def numbering_gaps(tasks: list[dict]) -> int:
    """Число пропущенных номеров упражнений внутри параграфов.

    Порядко-независимо: берём МНОЖЕСТВО номеров параграфа и считаем
    отсутствующие в [min..max]. Двухколоночная вёрстка (1,4,2,5,3,6) ложных
    разрывов не даёт, реальный пропуск (70, 72 без 71) — ловится.

    В отличие от прототипа mathocr разделы не угадываются по сбросу номера
    на 1 — здесь есть настоящий `paragraph` из `textbook_tasks`.
    """
    by_para: dict[str, set[int]] = {}
    for t in tasks:
        n = int_prefix(t.get("number"))
        if n is None:
            continue
        by_para.setdefault(str(t.get("paragraph", "")), set()).add(n)

    gaps = 0
    for nums in by_para.values():
        if len(nums) < 2:
            continue
        gaps += sum(1 for e in range(min(nums), max(nums) + 1) if e not in nums)
    return gaps


def missing_numbers(tasks: list[dict]) -> dict[str, list[int]]:
    """Какие именно номера пропущены, по параграфам. Для отчёта, не метрика."""
    by_para: dict[str, set[int]] = {}
    for t in tasks:
        n = int_prefix(t.get("number"))
        if n is None:
            continue
        by_para.setdefault(str(t.get("paragraph", "")), set()).add(n)

    out: dict[str, list[int]] = {}
    for para, nums in by_para.items():
        if len(nums) < 2:
            continue
        miss = [e for e in range(min(nums), max(nums) + 1) if e not in nums]
        if miss:
            out[para] = miss
    return out


def latex_ned(golden: list[dict], tasks: list[dict]) -> float | None:
    """Средний NED формул против golden.

    Для каждой golden-формулы берём лучшее совпадение среди формул задачи,
    совпавшей по ключу. Golden-формула, не найденная нигде, даёт NED = 1.
    Golden без формул в метрику не входит (словесные задачи).
    """
    if not golden:
        return None
    by_key = {_key(t): t for t in tasks}
    scores: list[float] = []
    for g in golden:
        gold_formulas = [canonicalize(f) for f in _golden_formulas(g)]
        gold_formulas = [f for f in gold_formulas if f]
        if not gold_formulas:
            continue
        found = by_key.get(_key(g))
        cand = extract_formulas(_task_text(found)) if found else []
        for gf in gold_formulas:
            scores.append(min((_ned(gf, c) for c in cand), default=1.0))
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def _golden_formulas(g: dict) -> list[str]:
    """Формулы golden-записи: явное поле `formulas`, иначе из текста."""
    explicit = g.get("formulas")
    if explicit:
        return list(explicit)
    return extract_formulas_raw(
        " ".join(str(g.get(f) or "") for f in ("question_md", "answer_md"))
    )


def default_compiler() -> Callable[[list[str]], list[bool]] | None:
    """KaTeX-компилятор, если Node и пакет доступны, иначе None.

    Отсутствие KaTeX — не ошибка: метрика станет «—», остальные посчитаются.
    """
    from src.validate import katex

    return katex.compile_formulas if katex.is_available() else None


def formula_compile_rate(
    tasks: list[dict], compiler: Callable[[list[str]], list[bool]] | None = None
) -> float | None:
    """Доля компилирующихся формул. Нет компилятора и KaTeX недоступен → None.

    Формулы берутся СЫРЫЕ (не канонизованные) — измеряем запись как есть.

    **Осторожно при трактовке:** compile_rate = 1.0 НЕ значит «формулы верны».
    Часть OCR-артефактов даёт валидный, но семантически неверный рендер
    (`rac{1}{2}`, `x \\\\cdot y`) и проходит компиляцию молча. Их ловит
    `src/validate/latex_artifacts.py`, а не эта метрика.
    """
    if compiler is None:
        compiler = default_compiler()
    if compiler is None:
        return None
    formulas = [f for t in tasks for f in extract_formulas_raw(_task_text(t))]
    if not formulas:
        return None
    results = compiler(formulas)
    if not results:
        return None
    return round(sum(1 for r in results if r) / len(results), 4)


def answer_join_coverage(tasks: list[dict]) -> float | None:
    """Доля задач с ответом ИЗ КНИГИ (`book_key` или `book_solution`).

    Интегральный индикатор: низкое покрытие значит, что номера теряются или
    искажаются раньше по пайплайну. Нет колонки — None, а не 0.0, чтобы не
    путать «не измеряли» с «измерили и ноль».

    Считаются оба книжных источника, а не только `book_key`: ответ, напечатанный
    рядом с условием в теле книги, ничем не хуже ответа из раздела «Ответы» —
    он тоже не выдуман. Список книжных источников один на проект и живёт
    в `src/pipeline/provenance.py` (`FROM_BOOK`).
    """
    if not tasks:
        return None
    if all(t.get("answer_source") is None for t in tasks):
        return None
    from src.pipeline.provenance import FROM_BOOK

    from_book = sum(1 for t in tasks if t.get("answer_source") in FROM_BOOK)
    return round(from_book / len(tasks), 4)


def evaluate(
    tasks: list[dict],
    golden: list[dict],
    label: str,
    compiler: Callable[[list[str]], list[bool]] | None = None,
) -> dict:
    """Собрать все метрики в одну запись."""
    return {
        "label": label,
        "n_tasks": len(tasks),
        "n_golden": len(golden),
        "task_recall": task_recall(golden, tasks),
        "formula_compile_rate": formula_compile_rate(tasks, compiler),
        "numbering_gaps": numbering_gaps(tasks),
        "latex_ned": latex_ned(golden, tasks),
        "answer_join_coverage": answer_join_coverage(tasks),
    }


def format_row(m: dict, note: str = "") -> str:
    """Строка для таблицы EVAL.md."""
    def f(v: object, nd: int = 4) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:.{nd}f}"
        return str(v)

    from datetime import date

    return (
        f"| {date.today().isoformat()} | {m['label']} | {f(m['task_recall'])} | "
        f"{f(m['formula_compile_rate'])} | {f(m['numbering_gaps'])} | "
        f"{f(m['latex_ned'])} | {f(m['answer_join_coverage'])} | "
        f"{m['n_tasks']} | {note} |"
    )
