"""Detect theme / section headers in OCR text (Uzbek school math 6)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MarkerKind = Literal["theme", "repetition", "self_test", "chapter"]


@dataclass
class ThemeMarker:
    kind: MarkerKind
    number: str  # e.g. "1-2", "3", "Тест I"
    title: str
    line: str
    offset: int  # char offset in page text


def _norm_dash(s: str) -> str:
    return s.replace("–", "-").replace("—", "-").strip()


# Actual G6 patterns seen in OCR:
#   ### 1–2 Делители..., ### **6–7** Признаки..., ### $3-5$ Признаки...,
#   ## § 1. ..., § 1–2. ..., 1–2 Натуральные...
# Actual G6 patterns seen in OCR:
#   ### 1–2 Делители..., ### **6–7** Признаки..., ### $3-5$ Признаки...,
#   ## § 1. ..., § 1–2. ..., 1–2 Натуральные...
_THEME_RANGE = re.compile(
    r"(?:^|\n)\s*"
    r"(?:#{1,4}\s*)?"            # optional ### / ####
    r"(?:\*{1,2}|§\s*|\$)?"     # optional opening ** or § or $
    r"(\d+)\s*[\–—\-]\s*(\d+)"  # N–M
    r"(?:\$|\*{1,2})?\.?\s+"    # optional closing $ or ** then optional dot
    r"([А-ЯA-ZЁ][^\n*\$]{4,80}?)"
    r"\s*\*{0,2}\s*(?:\n|$)",
    re.M,
)

# ## § 1. Деление..., # 10 Простые, § 10. Простые, **10** Простые
_THEME_SINGLE = re.compile(
    r"(?:^|\n)\s*"
    r"(?:#{1,4}\s*)?"
    r"(?:\*{1,2}|§\s*|\$)?"
    r"(\d{1,3})"
    r"(?:\$|\*{1,2})?\.?\s+"
    r"([А-ЯA-ZЁ][^\n*\$]{4,80}?)"
    r"\s*\*{0,2}\s*(?:\n|$)",
    re.M,
)

# ### 1. Натуральные числа  (повторение)
_REPETITION = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*)?"
    r"(\d{1,2})\.\s+"
    r"(Натуральн|Обыкновенн|Десятичн|Процент)[^\n]{0,60}",
    re.M | re.I,
)

_SELF_TEST = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*|\*{0,2})?"
    r"(?:Тест\s+([IVX]+|\d+)|"
    r"(Проверьте\s+себя!?))"
    r"[^\n]{0,40}",
    re.M | re.I,
)

# B9: паттерн `_CHAPTER` («§ N. Название» / «N. Название») удалён как мёртвый.
# Он был объявлен, но никогда не использовался в `find_markers`, и подключать
# его было бы ошибкой: это строгое подмножество `_THEME_SINGLE`, поэтому те же
# заголовки получили бы вид `chapter` с приоритетом выше `theme` — обычный
# параграф стал бы главой и сломал сегментацию. Настоящая глава ловится
# `_GLAva` («Глава N»), и она осталась.

_GLAva = re.compile(
    r"(?:^|\n)\s*(?:#{0,3}\s*)?"
    r"Глава\s+([IVX]+|\d+)\.\s*([^\n]{5,80})",
    re.M | re.I,
)


# При совпадении offset побеждает более специфичный маркер, а не тот, что раньше
# добавлен. `theme` — общий паттерн «номер + заголовок с большой буквы», он матчит
# и «### 2. Обыкновенные дроби» (повторение), и «Тест I». Специфичные паттерны
# опознают закрытый словарь (темы повторения) или явное ключевое слово.
_KIND_PRIORITY: dict[str, int] = {
    "self_test": 0,   # явное «Тест N» / «Проверьте себя»
    "repetition": 1,  # закрытый словарь тем повторения
    "chapter": 2,     # явное «Глава N»
    "theme": 3,       # общий паттерн — фолбэк
}


def find_markers(text: str) -> list[ThemeMarker]:
    """All theme boundaries in text, sorted by offset."""
    found: list[ThemeMarker] = []

    for m in _THEME_RANGE.finditer(text):
        num = f"{m.group(1)}-{m.group(2)}"
        title = m.group(3).strip().rstrip("*").strip()
        found.append(ThemeMarker("theme", num, title, m.group(0).strip(), m.start()))

    for m in _THEME_SINGLE.finditer(text):
        if any(f.offset == m.start() for f in found):
            continue
        num = m.group(1)
        title = m.group(2).strip().rstrip("*").strip()
        # skip exercise lines like "30. Запишите"
        if re.match(r"^\d+\.\s+[А-Я]", title) and len(num) >= 2:
            continue
        found.append(ThemeMarker("theme", num, title, m.group(0).strip(), m.start()))

    for m in _REPETITION.finditer(text):
        num = m.group(1)
        title = m.group(0).strip()
        found.append(ThemeMarker("repetition", num, title, m.group(0).strip(), m.start()))

    for m in _SELF_TEST.finditer(text):
        test_num = m.group(1) or ""
        label = "Проверьте себя"
        number = f"Тест {test_num}" if test_num else "Проверьте себя"
        found.append(ThemeMarker("self_test", number, label, m.group(0).strip(), m.start()))

    for m in _GLAva.finditer(text):
        found.append(
            ThemeMarker(
                "chapter",
                f"Глава {m.group(1)}",
                m.group(2).strip(),
                m.group(0).strip(),
                m.start(),
            )
        )

    # Сортировка по offset, при равенстве — по специфичности маркера, чтобы
    # дедуп ниже оставлял специфичный, а не первый добавленный.
    found.sort(key=lambda x: (x.offset, _KIND_PRIORITY.get(x.kind, 99)))
    # dedupe same offset
    out: list[ThemeMarker] = []
    seen: set[int] = set()
    for f in found:
        if f.offset in seen:
            continue
        seen.add(f.offset)
        out.append(f)
    return out


def split_text_at_markers(text: str, markers: list[ThemeMarker]) -> list[tuple[ThemeMarker | None, str]]:
    """Split page text into (marker_before_chunk, chunk_text) pairs."""
    if not markers:
        return [(None, text)]

    parts: list[tuple[ThemeMarker | None, str]] = []
    pos = 0
    for i, mk in enumerate(markers):
        if mk.offset > pos:
            parts.append((None if i == 0 else markers[i - 1], text[pos:mk.offset]))
        parts.append((mk, ""))
        pos = mk.offset + len(mk.line)
    if pos < len(text):
        parts.append((markers[-1], text[pos:]))
    return parts
