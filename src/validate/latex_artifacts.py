"""Детектор и ремонт OCR-артефактов бэкслеша в LaTeX (Сессия 2, B5).

**Зачем отдельно от компиляции KaTeX.** Замерено на реальных артефактах
(см. PROGRESS.md, С2): гейт компиляции ловит только те поломки, что ломают
разбор. Артефакты, дающие валидный, но **семантически неверный** рендер,
проходят молча:

    \\left(\\frac{14\\pi}{3}ight)   → БИТО   (\\left без пары)  — ловит KaTeX
    150^\\\\circ                    → БИТО   (\\\\ в степени)    — ловит KaTeX
    x^2 \\\\cdot y                  → OK     — но \\\\ здесь перенос строки, не умножение
    rac{1}{2}                       → OK     — рендерится как текст «rac{1}{2}»

Последние два — тихая порча содержания: ученик увидит бессмыслицу, а
`compile_rate` покажет 1.0. Поэтому нужен лексический детектор.

Все функции чистые. Массовый ремонт в БД — `scripts/audit_latex_compile.py`
(с `--dry-run` и бэкапом), не отсюда.
"""
from __future__ import annotations

import re

# ── Потерянный ведущий бэкслеш ────────────────────────────────────────────
# `\frac{` → `rac{`, `\right)` → `ight)`, `\left(` → `eft(`.
# Требуем характерный контекст (скобка/фигурная), иначе поймаем обычные слова.
_LOST_BACKSLASH = (
    (re.compile(r"(?<![\\A-Za-z])rac\s*\{"), r"\\frac{", "потерян \\ в \\frac"),
    (re.compile(r"(?<![\\A-Za-z])ight\s*([)\]}|.])"), r"\\right\1", "потерян \\ в \\right"),
    (re.compile(r"(?<![\\A-Za-z])eft\s*([(\[{|.])"), r"\\left\1", "потерян \\ в \\left"),
    (re.compile(r"(?<![\\A-Za-z])sqrt\s*[{\[]"), r"\\sqrt", "потерян \\ в \\sqrt"),
)

# ── Задвоенный бэкслеш перед именем команды ───────────────────────────────
# `\\circ` → `\circ`. Настоящий перенос строки (`\\`) за собой имени команды
# не тянет — он идёт перед пробелом, переводом строки или концом. Поэтому
# «\\ + буквы» — почти наверняка артефакт, а не вёрстка.
# ВАЖНО: в матрицах/массивах `\\` легитимен, но там он не липнет к букве.
_DOUBLED_BACKSLASH = re.compile(r"\\\\([a-zA-Z]+)")


def find_artifacts(latex: str) -> list[str]:
    """Список описаний найденных артефактов. Пусто — чисто.

    Не бросает и не чинит: используется и для отчёта, и для гейта.
    """
    if not latex:
        return []
    found: list[str] = []
    for pattern, _repl, why in _LOST_BACKSLASH:
        if pattern.search(latex):
            found.append(why)
    for m in _DOUBLED_BACKSLASH.finditer(latex):
        found.append(f"задвоенный \\\\ перед \\{m.group(1)}")
    return found


def has_artifacts(latex: str) -> bool:
    return bool(find_artifacts(latex))


def repair(latex: str) -> str:
    """Починить детерминированные артефакты. Неоднозначное не трогает.

    Идемпотентна: повторный вызов ничего не меняет.
    """
    if not latex:
        return latex
    s = latex
    for pattern, repl, _why in _LOST_BACKSLASH:
        s = pattern.sub(repl, s)
    s = _DOUBLED_BACKSLASH.sub(r"\\\1", s)
    return s


def repair_report(latex: str) -> tuple[str, list[str]]:
    """`(починенное, что_чинили)`. Для `--dry-run`: показать диф, не записывая."""
    before = find_artifacts(latex)
    return repair(latex), before
