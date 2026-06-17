"""TOC-экстрактор: достаёт оглавление учебника либо из закладок PDF, либо через Gemini Pro Vision.

Используется CLI-скриптом `scripts/ingest_textbook.py` перед регистрацией учебника.

Стратегия:
1. Сначала пробуем `fitz.get_toc()` — у современных PDF обычно есть закладки.
2. Если закладок нет или их меньше 3 — рендерим первые N страниц (по умолчанию 20)
   в PNG и просим Gemini Pro извлечь TOC в нашем формате.
3. Нормализуем уровни (1=глава, 2=параграф, 3=тема, 4=подтема) и сортировку.

Возвращаемый формат совместим с `DBWriter.write_toc`:
[
    {"number": "1", "title": "Натуральные числа", "level": 1, "page_start": 5, "page_end": 50},
    {"number": "1.1", "title": "Десятичная запись", "level": 2, "parent_number": "1",
     "page_start": 5, "page_end": 12, "sort_order": 1},
    ...
]
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF

from src.pipeline.gemini_client import (
    call_gemini_vision,
    get_flash_model,
    get_pro_model,
    parse_json_response,
)

log = logging.getLogger(__name__)

_TOC_DPI = 150  # достаточно для текста оглавления
_FIRST_PAGES_FOR_LLM = 12  # сколько страниц с начала PDF отдавать LLM
_LAST_PAGES_FOR_LLM = 20   # оглавление часто в конце (Виленкин, Макарычev и др.)
_MIN_BOOKMARKS = 3  # если в PDF меньше — лучше идти в LLM


_LLM_PROMPT = """\
Ты — эксперт по школьным учебникам математики. Это страницы PDF учебника.
Найди и извлеки ОГЛАВЛЕНИЕ (содержание) учебника в виде структурированного JSON.

ВАЖНО: оглавление может быть в КОНЦЕ книги (перед приложениями: ответы, указатель),
а не в начале — особенно у сканов Виленкина, Макарычева и др.

ТРЕБОВАНИЯ К ВЫВОДУ:
Верни массив объектов:
[
  {
    "number": "1",          // номер раздела как в книге ("1", "§3", "3.1", "Глава 2")
    "title": "...",         // название без номера
    "level": 1,             // 1=глава, 2=параграф, 3=тема/пункт, 4=подтема
    "parent_number": "",    // number родителя ("" для верхнего уровня)
    "page_start": 5,        // страница из оглавления (если указана), иначе null
    "page_end": null,       // обычно null — конец вычислим
    "sort_order": 1         // порядок в книге
  },
  ...
]

ПРАВИЛА:
- Иерархия: глава → параграф → тема. Используй level аккуратно:
  • level=1 — главы/разделы верхнего уровня («Глава 1», «Раздел I»)
  • level=2 — параграфы (§1, §1.1) или нумерованные подразделы
  • level=3 — темы внутри параграфа
  • level=4 — подтемы (используй редко)
- parent_number ссылается на number ближайшего родителя.
- Если в книге только параграфы без глав — все level=2 без parent.
- НЕ выдумывай записи, которых нет в видимом тексте.
- НЕ включай служебные элементы: «Введение», «Ответы», «Предметный указатель»,
  «Список литературы» — если они не являются полноценными разделами с задачами.
- Только JSON-массив, без markdown-обёртки.
"""


def _render_first_pages(pdf_path: str, n: int) -> List[Dict[str, str]]:
    """Рендерит первые `n` страниц PDF в PNG (base64) для Gemini Vision."""
    parts: List[Dict[str, str]] = []
    with fitz.open(pdf_path) as doc:
        total = min(n, doc.page_count)
        for i in range(total):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=_TOC_DPI)
            b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
            parts.append({"mimeType": "image/png", "data": b64})
    return parts


def _render_last_pages(pdf_path: str, n: int) -> List[Dict[str, str]]:
    """Рендерит последние `n` страниц PDF в PNG (base64) для Gemini Vision."""
    parts: List[Dict[str, str]] = []
    with fitz.open(pdf_path) as doc:
        total = doc.page_count
        start = max(0, total - n)
        for i in range(start, total):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=_TOC_DPI)
            b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
            parts.append({"mimeType": "image/png", "data": b64})
    return parts


def _from_pdf_bookmarks(pdf_path: str) -> List[Dict[str, Any]]:
    """Конвертирует встроенные закладки PDF в наш формат TOC."""
    entries: List[Dict[str, Any]] = []
    with fitz.open(pdf_path) as doc:
        toc = doc.get_toc(simple=True)  # [[level, title, page], ...]

    if not toc or len(toc) < _MIN_BOOKMARKS:
        return []

    # parent stack: индекс level → последний number этого уровня
    parent_stack: Dict[int, str] = {}

    for sort_idx, (lvl, raw_title, page) in enumerate(toc):
        lvl = max(1, min(4, int(lvl)))
        title_clean = (raw_title or "").strip()

        # Пытаемся вытащить «номер» из начала названия: «§3.1 Дроби» → number="3.1"
        m = re.match(r"^(?:§\s*)?([0-9]+(?:\.[0-9]+)*|[IVX]+)\s*[.\)]?\s*(.*)$", title_clean)
        if m:
            number = m.group(1)
            title = m.group(2).strip() or title_clean
        else:
            number = f"_{sort_idx + 1}"  # синтетический
            title = title_clean

        # Найти ближайшего родителя (level < текущего)
        parent_number = ""
        for plvl in range(lvl - 1, 0, -1):
            if plvl in parent_stack:
                parent_number = parent_stack[plvl]
                break

        entries.append({
            "number": number,
            "title": title,
            "level": lvl,
            "parent_number": parent_number,
            "page_start": int(page) if page else None,
            "page_end": None,
            "sort_order": sort_idx,
        })

        parent_stack[lvl] = number
        # Чистим стек ниже текущего уровня (новая глава отменяет старые подпункты)
        for k in list(parent_stack.keys()):
            if k > lvl:
                parent_stack.pop(k, None)

    return entries


def _robust_parse_json(text: str) -> object:
    """Parse JSON from LLM output that may be wrapped in markdown or truncated.

    Strategy:
    1. Try raw json.loads (clean response)
    2. Strip ```json ... ``` fence
    3. Extract from first '[' to last ']' (handles extra prose around the array)
    4. Recover truncated array by slicing to last complete '}'
    """
    import json as _json
    text = text.strip()

    # 1. Direct parse
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        pass

    # 2. Markdown fence (may be unclosed)
    m = re.search(r"```(?:json)?\s*(.*?)(?:```|$)", text, re.DOTALL)
    if m:
        candidate = m.group(1).strip()
        try:
            return _json.loads(candidate)
        except _json.JSONDecodeError:
            text = candidate  # continue with de-fenced text below

    # 3. Find first '[' ... last ']'
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return _json.loads(candidate)
        except _json.JSONDecodeError:
            # 4. Truncated: trim to last complete object '}' before a ',' or ']'
            last_obj = candidate.rfind("},")
            if last_obj == -1:
                last_obj = candidate.rfind("}")
            if last_obj != -1:
                recovered = candidate[: last_obj + 1] + "]"
                try:
                    result = _json.loads(recovered)
                    log.warning("TOC LLM: response was truncated; recovered %d entries", len(result))
                    return result
                except _json.JSONDecodeError:
                    pass

    log.error("TOC LLM: could not parse response (len=%d)", len(text))
    return []


def _from_llm(pdf_path: str) -> List[Dict[str, Any]]:
    """Вытаскивает TOC через Gemini Pro Vision.

    Стратегия:
    1. Пробуем первые _FIRST_PAGES_FOR_LLM страниц (оглавление обычно в начале).
    2. Если нашли < 3 записей — пробуем последние _LAST_PAGES_FOR_LLM страниц
       (некоторые сканы имеют оглавление в конце, напр. Виленкин).
    """
    image_parts = _render_first_pages(pdf_path, _FIRST_PAGES_FOR_LLM)
    if not image_parts:
        return []

    log.info("TOC: calling Gemini Vision on first %d pages of %s",
             len(image_parts), Path(pdf_path).name)

    raw = call_gemini_vision(
        _LLM_PROMPT,
        image_parts,
        model=get_pro_model(),
        temperature=0.1,
        max_tokens=8192,
        timeout=300,
        response_mime_type="application/json",
    )
    parsed = _robust_parse_json(raw)
    if isinstance(parsed, dict):
        parsed = parsed.get("toc") or parsed.get("entries") or []
    if not isinstance(parsed, list):
        log.warning("TOC LLM returned unexpected shape: %s", type(parsed))
        parsed = []

    # Всегда проверяем последние страницы — у скан-книг оглавление бывает в конце.
    # Берём результат с большим числом записей.
    log.info("TOC: also trying last %d pages of %s",
             _LAST_PAGES_FOR_LLM, Path(pdf_path).name)
    last_parts = _render_last_pages(pdf_path, _LAST_PAGES_FOR_LLM)
    if last_parts:
        raw2 = call_gemini_vision(
            _LLM_PROMPT,
            last_parts,
            model=get_flash_model(),
            temperature=0.1,
            max_tokens=8192,
            timeout=180,
        )
        parsed2 = _robust_parse_json(raw2)
        if isinstance(parsed2, dict):
            parsed2 = parsed2.get("toc") or parsed2.get("entries") or []
        if isinstance(parsed2, list) and len(parsed2) > len(parsed):
            log.info("TOC: last pages gave more entries (%d > %d) for %s — using last pages result",
                     len(parsed2), len(parsed), Path(pdf_path).name)
            parsed = parsed2

    entries: List[Dict[str, Any]] = []
    for sort_idx, item in enumerate(parsed):
        if not isinstance(item, dict):
            continue
        number = str(item.get("number", "")).strip() or f"_{sort_idx + 1}"
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        lvl = max(1, min(4, int(item.get("level", 2))))
        entries.append({
            "number": number,
            "title": title,
            "level": lvl,
            "parent_number": str(item.get("parent_number", "")).strip(),
            "page_start": item.get("page_start"),
            "page_end": item.get("page_end"),
            "sort_order": int(item.get("sort_order", sort_idx)),
        })
    return entries


def _fill_page_end(entries: List[Dict[str, Any]], total_pages: Optional[int]) -> None:
    """Если page_end не указан — берём page_start следующей записи того же или верхнего уровня."""
    starts = [(i, e.get("page_start")) for i, e in enumerate(entries) if e.get("page_start")]
    for idx, entry in enumerate(entries):
        if entry.get("page_end") is not None or entry.get("page_start") is None:
            continue
        cur_page = entry["page_start"]
        cur_lvl = entry.get("level", 2)
        next_page = None
        for j in range(idx + 1, len(entries)):
            nxt = entries[j]
            if nxt.get("page_start") and nxt.get("page_start") > cur_page \
                    and nxt.get("level", 2) <= cur_lvl:
                next_page = nxt["page_start"] - 1
                break
        if next_page is None and total_pages:
            next_page = total_pages
        if next_page:
            entry["page_end"] = next_page


def extract_toc(pdf_path: str, *, force_llm: bool = False) -> List[Dict[str, Any]]:
    """Главная точка входа.

    1. Пытается достать TOC из встроенных закладок PDF.
    2. Если их < 3 или `force_llm=True` — вызывает Gemini Pro Vision.
    3. Заполняет page_end по соседям.
    """
    pdf_path = str(pdf_path)
    total_pages: Optional[int] = None
    try:
        with fitz.open(pdf_path) as doc:
            total_pages = doc.page_count
    except Exception as exc:
        log.warning("Failed to open PDF %s: %s", pdf_path, exc)

    entries: List[Dict[str, Any]] = []
    if not force_llm:
        entries = _from_pdf_bookmarks(pdf_path)
        if entries:
            log.info("TOC: %d entries from PDF bookmarks (%s)", len(entries), Path(pdf_path).name)

    if not entries:
        entries = _from_llm(pdf_path)
        log.info("TOC: %d entries from Gemini Pro Vision (%s)", len(entries), Path(pdf_path).name)

    _fill_page_end(entries, total_pages)
    return entries
