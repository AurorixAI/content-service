#!/usr/bin/env python3
"""Scan Makarychev 7 PDF for paragraph start pages via OCR (uses pipeline cache).

Finds `### N. Title` headers and footer page numbers in cached/batch OCR.
Prints JSON list suitable for insert_toc_makarychev7.py.

Usage (inside content-worker):
    python /app/scripts/scan_makarychev7_toc.py \\
        --pdf /textbooks/7_grade/1701411287_algebra_-uchebnik_-7-kl_-makarychev_compressed.pdf
"""
from __future__ import annotations

import argparse
import json
import re
import sys

sys.path.insert(0, "/app")

from src.pipeline.ocr import GeminiVisionOCR

# Makarychev 2023 (15th ed.) — chapters and § sections for parent mapping
STRUCTURE = [
    ("I", "ВЫРАЖЕНИЯ, ТОЖДЕСТВА, УРАВНЕНИЯ", [
        ("1", "ЧИСЛА И ВЫРАЖЕНИЯ", range(1, 5)),
        ("2", "ПРЕОБРАЗОВАНИЕ ВЫРАЖЕНИЙ", range(5, 7)),
        ("3", "УРАВНЕНИЯ С ОДНОЙ ПЕРЕМЕННОЙ", range(7, 11)),
    ]),
    ("II", "ФУНКЦИИ", [
        ("4", "ФУНКЦИИ И ИХ ГРАФИКИ", range(11, 15)),
        ("5", "ЛИНЕЙНАЯ ФУНКЦИЯ", range(15, 18)),
    ]),
    ("III", "СТЕПЕНЬ С НАТУРАЛЬНЫМ ПОКАЗАТЕЛЕМ", [
        ("6", "СТЕПЕНЬ И ЕЁ СВОЙСТВА", range(18, 21)),
        ("7", "ОДНОЧЛЕНЫ", range(21, 25)),
    ]),
    ("IV", "МНОГОЧЛЕНЫ", [
        ("8", "СУММА И РАЗНОСТЬ МНОГОЧЛЕНОВ", range(25, 27)),
        ("9", "ПРОИЗВЕДЕНИЕ ОДНОЧЛЕНА И МНОГОЧЛЕНА", range(27, 29)),
        ("10", "ПРОИЗВЕДЕНИЕ МНОГОЧЛЕНОВ", range(29, 32)),
    ]),
    ("V", "ФОРМУЛЫ СОКРАЩЁННОГО УМНОЖЕНИЯ", [
        ("11", "КВАДРАТ СУММЫ И КВАДРАТ РАЗНОСТИ", range(32, 34)),
        ("12", "РАЗНОСТЬ КВАДРАТОВ. СУММА И РАЗНОСТЬ КУБОВ", range(34, 37)),
        ("13", "ПРЕОБРАЗОВАНИЕ ЦЕЛЫХ ВЫРАЖЕНИЙ", range(37, 40)),
    ]),
    ("VI", "СИСТЕМЫ ЛИНЕЙНЫХ УРАВНЕНИЙ", [
        ("14", "ЛИНЕЙНЫЕ УРАВНЕНИЯ С ДВУМЯ ПЕРЕМЕННЫМИ И ИХ СИСТЕМЫ", range(40, 43)),
        ("15", "РЕШЕНИЕ СИСТЕМ ЛИНЕЙНЫХ УРАВНЕНИЙ", range(43, 47)),
    ]),
]

# Fallback titles when OCR title is garbled (2023 edition)
TITLES = {
    1: "Рациональные числа",
    2: "Числовые выражения",
    3: "Выражения с переменными",
    4: "Сравнение значений выражений",
    5: "Свойства действий над числами",
    6: "Тождества. Тождественные преобразования выражений",
    7: "Уравнение и его корни",
    8: "Линейное уравнение с одной переменной",
    9: "Решение задач с помощью уравнений",
    10: "Формулы",
    11: "Числовые промежутки",
    12: "Что такое функция",
    13: "Вычисление значений функции по формуле",
    14: "График функции",
    15: "Прямая пропорциональность и её график",
    16: "Линейная функция и её график",
    17: "Кусочно-заданные функции",
    18: "Определение степени с натуральным показателем",
    19: "Умножение и деление степеней",
    20: "Возведение в степень произведения и степени",
    21: "Одночлен и его стандартный вид",
    22: "Умножение одночленов. Возведение одночлена в степень",
    23: "Функции y = x² и y = x³ и их графики",
    24: "О простых и составных числах",
    25: "Многочлен и его стандартный вид",
    26: "Сложение и вычитание многочленов",
    27: "Умножение одночлена на многочлен",
    28: "Вынесение общего множителя за скобки",
    29: "Умножение многочлена на многочлен",
    30: "Разложение многочлена на множители способом группировки",
    31: "Деление с остатком",
    32: "Возведение в квадрат и в куб суммы и разности двух выражений",
    33: "Разложение на множители с помощью формул квадрата суммы и квадрата разности",
    34: "Умножение разности двух выражений на их сумму",
    35: "Разложение разности квадратов на множители",
    36: "Разложение на множители суммы и разности кубов",
    37: "Преобразование целого выражения в многочлен",
    38: "Применение различных способов для разложения на множители",
    39: "Возведение двучлена в степень",
    40: "Линейное уравнение с двумя переменными",
    41: "График линейного уравнения с двумя переменными",
    42: "Системы линейных уравнений с двумя переменными",
    43: "Способ подстановки",
    44: "Способ сложения",
    45: "Решение задач с помощью систем уравнений",
    46: "Линейные неравенства с двумя переменными и их системы",
}


def _scan_pdf(pdf_path: str, batch: int = 15) -> dict[int, tuple[int, str]]:
    """Return {paragraph_num: (page_start, title)} from OCR."""
    import fitz

    ocr = GeminiVisionOCR()
    with fitz.open(pdf_path) as doc:
        total = doc.page_count

    found: dict[int, tuple[int, str]] = {}
    for start in range(1, total + 1, batch):
        end = min(start + batch - 1, total)
        text = ocr.process_pages(pdf_path, start, end, figures_by_page={})
        pages = re.split(r"--- страница ---", text)
        for chunk in pages:
            foot = re.findall(r"\*\*(\d{1,3})\*\*\s*$", chunk, re.M)
            foot += re.findall(r"\|\s*(\d{1,3})\s*(?:\||$)", chunk, re.M)
            page = int(foot[-1]) if foot else None
            for mm in re.finditer(r"^#{1,3}\s*(\d+)\.\s+(.+)$", chunk, re.M):
                num = int(mm.group(1))
                title = mm.group(2).strip()
                if num < 1 or num > 46:
                    continue
                p = page if page else start
                if num not in found or p < found[num][0]:
                    found[num] = (p, title)
        print(f"  scanned p{start}-{end}, found {len(found)} paragraphs", flush=True)
    return found


def _fill_gaps(found: dict[int, tuple[int, str]], total_pages: int) -> dict[int, int]:
    """Ensure pages 1-46; interpolate missing from neighbours."""
    pages: dict[int, int] = {n: found[n][0] for n in found}
    # Known anchors from manual verification / prior job
    anchors = {1: 5, 2: 11, 3: 14, 4: 19, 9: 39, 10: 42, 13: 59, 14: 61,
               16: 73, 17: 75, 25: 129, 27: 137, 29: 147, 37: 185, 40: 201, 43: 213}
    for n, p in anchors.items():
        pages[n] = p

    for n in range(1, 47):
        if n not in pages:
            prev = next((pages[k] for k in range(n - 1, 0, -1) if k in pages), 5)
            nxt = next((pages[k] for k in range(n + 1, 47) if k in pages), total_pages)
            pages[n] = min(prev + 2, nxt - 1)
        pages[n] = max(5, min(pages[n], total_pages))

    # Enforce strictly increasing
    for n in range(2, 47):
        if pages[n] <= pages[n - 1]:
            pages[n] = pages[n - 1] + 1
    return pages


def build_toc(pdf_path: str, *, scan: bool = True) -> list[dict]:
    import fitz

    with fitz.open(pdf_path) as doc:
        total_pages = doc.page_count

    found = _scan_pdf(pdf_path) if scan else {}
    page_map = _fill_gaps(found, total_pages)

    entries: list[dict] = []
    sort_order = 0
    for ch_num, ch_title, sections in STRUCTURE:
        ch_key = f"Глава {ch_num}"
        entries.append({
            "number": ch_key,
            "title": ch_title,
            "level": 1,
            "parent_number": "",
            "page_start": page_map.get(next(iter(sections[0][2])), 5),
            "page_end": None,
            "sort_order": sort_order,
        })
        sort_order += 1

        for sec_num, sec_title, para_range in sections:
            sec_key = f"§{sec_num}"
            first_para = para_range.start
            entries.append({
                "number": sec_key,
                "title": sec_title,
                "level": 2,
                "parent_number": ch_key,
                "page_start": page_map[first_para],
                "page_end": None,
                "sort_order": sort_order,
            })
            sort_order += 1

            for pnum in para_range:
                ocr_title = found.get(pnum, (page_map[pnum], ""))[1]
                title = TITLES[pnum]
                if ocr_title and len(ocr_title) > 5 and not ocr_title.startswith("$"):
                    title = ocr_title.split(".")[0][:120] if len(ocr_title) > 120 else ocr_title
                entries.append({
                    "number": str(pnum),
                    "title": title,
                    "level": 3,
                    "parent_number": sec_key,
                    "page_start": page_map[pnum],
                    "page_end": None,
                    "sort_order": sort_order,
                })
                sort_order += 1

    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--no-scan", action="store_true", help="Use anchors only (fast)")
    args = ap.parse_args()
    toc = build_toc(args.pdf, scan=not args.no_scan)
    print(json.dumps(toc, ensure_ascii=False, indent=2))
    leaves = [e for e in toc if e["level"] == 3]
    print(f"\n# Total entries: {len(toc)}, leaf paragraphs: {len(leaves)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
