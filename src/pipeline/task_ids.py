"""Канонический формат идентификаторов задач (`tasks_master.id`).

Формат задан не нами — он уже есть в продовой базе:

    id               = {prefix}_{параграф}_{номер}      G5_TB_10_161.1
    source_reference = {textbook_uuid}::{параграф}:{номер}

Здесь только одно добавление к сложившемуся: **части приводятся к ASCII**.
Замер на выгрузке прода (35 202 задачи, 2026-09-01) показал, что 8 020
идентификаторов (22.8 %) содержат не-ASCII — `G6_TB_40–42_353` с длинным тире,
`G10_TB_§22_22_5_1` с параграфным знаком, `G9_TB_УКГ4_429_2` кириллицей.
Плюс подпункт в одной и той же роли пишется то латиницей (1 184), то кириллицей
(1 513): `..._85_а` и `..._85_a` — разные строки, один и тот же подпункт книги.

Идентификатор — ключ, по которому задачу ищут в логах, URL и выгрузках. Такой
ключ обязан быть стабильным и печатаемым, поэтому нормализация детерминированная
и обратимой не притворяется: она нужна для уникальности, а человекочитаемая
привязка живёт в `source_reference`, `paragraph_number` и `exercise_number`,
где текст сохраняется как в книге.
"""

from __future__ import annotations

import re

#: Практическая транслитерация. Нужна не для красоты, а чтобы `УКГ4` и `Тест X`
#: не превращались в пустую строку и не схлопывали разные параграфы в один id.
_CYRILLIC: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

#: Знаки, которые в книге значат «параграф/номер», а в идентификаторе — мусор.
_DROP = "§№#*"

#: Разные тире из типографики PDF. Все они значат диапазон.
_DASHES = "‐‑‒–—―−"

_ALLOWED_RE = re.compile(r"[^A-Za-z0-9_-]")
_MULTI_US_RE = re.compile(r"_{2,}")

#: `tasks_master.id` — VARCHAR(60).
MAX_TASK_ID_LEN = 60


def transliterate(value: str) -> str:
    """Кириллица → латиница, регистр сохраняется."""
    out: list[str] = []
    for ch in value:
        low = ch.lower()
        if low in _CYRILLIC:
            rep = _CYRILLIC[low]
            out.append(rep.upper() if ch.isupper() and rep else rep)
        else:
            out.append(ch)
    return "".join(out)


def normalize_id_part(value: object) -> str:
    """Часть идентификатора → ASCII-безопасный вид.

    Точка становится подчёркиванием — так делает существующий писатель, и так
    выглядят идентификаторы, уже лежащие в проде. Менять это правило нельзя:
    оно определяет совместимость с 35 202 записанными задачами.
    """
    s = str(value or "").strip()
    if not s:
        return ""
    for ch in _DROP:
        s = s.replace(ch, "")
    for ch in _DASHES:
        s = s.replace(ch, "-")
    s = transliterate(s)
    s = s.replace(".", "_")
    s = re.sub(r"\s+", "", s)
    s = _ALLOWED_RE.sub("", s)
    s = _MULTI_US_RE.sub("_", s)
    return s.strip("_-")


def build_task_id(
    prefix: str,
    paragraph_number: object,
    exercise_number: object,
    *,
    max_len: int = MAX_TASK_ID_LEN,
) -> str:
    """`{prefix}_{параграф}_{номер}`, обрезанный до длины колонки.

    Пустые части выпадают, а не оставляют висящее подчёркивание: у задачи без
    параграфа id должен быть `G5_TB_161`, а не `G5_TB__161`.
    Если не осталось ничего, кроме префикса, возвращается пустая строка —
    вызывающий сам решает, чем адресовать задачу; молча выдать всем один и тот
    же `G5_TB` нельзя, это склеит их в одну строку при записи.
    """
    parts = [normalize_id_part(paragraph_number), normalize_id_part(exercise_number)]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return f"{normalize_id_part(prefix)}_{'_'.join(parts)}"[:max_len].rstrip("_-")


def build_source_reference(
    textbook_id: object,
    paragraph_number: object,
    exercise_number: object,
) -> str:
    """`{textbook_uuid}::{параграф}:{номер}` — как в проде.

    Здесь текст **не** нормализуется: это ссылка на место в книге для человека,
    и «§ 1.4, № 14.10.а» должно читаться так, как напечатано.
    """
    book = str(textbook_id or "").strip()
    para = str(paragraph_number or "").strip()
    ex = str(exercise_number or "").strip()
    if not book:
        return ""
    return f"{book}::{para}:{ex}"
