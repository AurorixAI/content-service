"""Канонизация LaTeX перед сравнением — фундамент всех метрик.

Перенесено из прототипа `newocr/mathocr/mathocr/eval/canonical.py` (Сессия 1).

**Зачем отдельно от `_latex_to_school` (`pipeline/answer_sympy_gate.py`).**
Это разные контракты, не дубль:

- `_latex_to_school` — LaTeX → школьная нотация **для показа человеку**
  (`\\frac{1}{2}` → `1/2`, `\\sqrt[3]{x}` → `∛(x)`), пробелы сохраняются.
- `canonicalize` (здесь) — LaTeX → **ключ сравнения**. Пробелы удаляются
  полностью, что для отображения было бы неверно, но для edit-distance
  необходимо: `x + 1` и `x+1` — одна и та же формула, метрика не должна
  штрафовать за косметику.

Использовать это только в метриках. Для показа — `_latex_to_school`.
"""
from __future__ import annotations

import re

_FRAC = re.compile(r"\\[dt]frac\b")
_LEFT_RIGHT = re.compile(r"\\(?:left|right)\b")
_CDOT = re.compile(r"\\cdot\b")
_MATHRM = re.compile(r"\\mathrm\s*\{")
_WS = re.compile(r"\s+")
_DOLLARS = re.compile(r"\${1,2}")


def canonicalize(latex: str) -> str:
    """Привести формулу к канонической форме для сравнения.

    - `\\dfrac|\\tfrac` → `\\frac`
    - `\\left(|\\right)` → `(|)` (убираем команды, разделитель остаётся)
    - `\\cdot` → `*`
    - `\\mathrm{…}` → `\\text{…}` (унификация текстовых вставок)
    - удаление всех пробелов
    """
    s = (latex or "").strip()
    s = _FRAC.sub(r"\\frac", s)
    s = _LEFT_RIGHT.sub("", s)
    s = _CDOT.sub("*", s)
    s = _MATHRM.sub(r"\\text{", s)
    s = _WS.sub("", s)
    return s


def strip_math_delimiters(md: str) -> str:
    """Убрать `$`/`$$` из извлечённого сегмента."""
    return _DOLLARS.sub("", md or "").strip()


def extract_formulas_raw(md: str) -> list[str]:
    """СЫРЫЕ LaTeX-сегменты из markdown: `$…$` и `$$…$$`.

    Без канонизации — как записано в источнике. Нужно там, где важна исходная
    запись: компиляция в KaTeX (Сессия 2), сборка confidence (Сессия 5).
    """
    formulas: list[str] = []
    # сначала выключные $$...$$, затем inline $...$ по остатку
    for m in re.finditer(r"\$\$(.+?)\$\$", md or "", flags=re.DOTALL):
        formulas.append(m.group(1).strip())
    without_display = re.sub(r"\$\$.+?\$\$", " ", md or "", flags=re.DOTALL)
    for m in re.finditer(r"\$(.+?)\$", without_display, flags=re.DOTALL):
        formulas.append(m.group(1).strip())
    return [f for f in formulas if f]


def extract_formulas(md: str) -> list[str]:
    """Канонизованные LaTeX-сегменты из markdown, в порядке появления."""
    return [c for c in (canonicalize(f) for f in extract_formulas_raw(md)) if c]
