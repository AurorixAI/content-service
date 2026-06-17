#!/usr/bin/env python3
"""OCR-scan Makarychev 7 PDF and detect exact paragraph start pages.

Usage:
    docker exec content-worker python /app/scripts/calibrate_makarychev7_pages.py
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, "/app")

import fitz
from src.pipeline.ocr import GeminiVisionOCR

PDF = "/textbooks/7_grade/1701411287_algebra_-uchebnik_-7-kl_-makarychev_compressed.pdf"
BATCH = 12


def _page_from_chunk(chunk: str, fallback: int) -> int | None:
    foot = re.findall(r"\*\*(\d{1,3})\*\*\s*$", chunk, re.M)
    foot += re.findall(r"\|\s*(\d{1,3})\s*$", chunk, re.M)
    foot += re.findall(r"^\s*(\d{1,3})\s*$", chunk, re.M)
    if foot:
        return int(foot[-1])
    return None


def scan() -> dict[int, tuple[int, str]]:
    doc = fitz.open(PDF)
    total = doc.page_count
    doc.close()

    ocr = GeminiVisionOCR()
    found: dict[int, tuple[int, str]] = {}

    for start in range(1, total + 1, BATCH):
        end = min(start + BATCH - 1, total)
        print(f"OCR {start}-{end}...", flush=True)
        text = ocr.process_pages(PDF, start, end, figures_by_page={})
        chunks = re.split(r"--- страница ---", text)
        for chunk in chunks:
            headers = list(re.finditer(r"^#{1,3}\s*(\d+)\.\s+(.+)$", chunk, re.M))
            if not headers:
                continue
            page = _page_from_chunk(chunk, start)
            for mm in headers:
                num = int(mm.group(1))
                if num < 1 or num > 46:
                    continue
                title = mm.group(2).strip()
                p = page if page else start
                if num not in found or p < found[num][0]:
                    found[num] = (p, title)

    return found


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
    32: "Возведение в квадрат и в куб суммы и разности",
    33: "Разложение на множители (квадрат суммы и разности)",
    34: "Умножение разности на сумму",
    35: "Разложение разности квадратов на множители",
    36: "Разложение на множители суммы и разности кубов",
    37: "Преобразование целого выражения в многочлен",
    38: "Применение различных способов разложения на множители",
    39: "Возведение двучлена в степень",
    40: "Линейное уравнение с двумя переменными",
    41: "График линейного уравнения с двумя переменными",
    42: "Системы линейных уравнений с двумя переменными",
    43: "Способ подстановки",
    44: "Способ сложения",
    45: "Решение задач с помощью систем уравнений",
    46: "Линейные неравенства с двумя переменными и их системы",
}


def _enforce_monotonic(pages: dict[int, int]) -> dict[int, int]:
    for n in range(2, 47):
        if pages[n] <= pages[n - 1]:
            pages[n] = pages[n - 1] + 1
    return pages


def _fill_missing(found: dict[int, tuple[int, str]], total: int) -> dict[int, int]:
    pages = {n: found[n][0] for n in found}
    for n in range(1, 47):
        if n not in pages:
            prev = next((pages[k] for k in range(n - 1, 0, -1) if k in pages), 5)
            nxt = next((pages[k] for k in range(n + 1, 47) if k in pages), total)
            pages[n] = min(prev + 1, nxt - 1)
        pages[n] = max(5, min(pages[n], total))
    return _enforce_monotonic(pages)


def main() -> int:
    found = scan()
    import fitz

    total = fitz.open(PDF).page_count
    pages = _fill_missing(found, total)

    print("\n=== DETECTED PARAGRAPH STARTS ===")
    for n in range(1, 47):
        src = "OCR" if n in found else "fill"
        p = pages[n]
        title = found[n][1][:60] if n in found else TITLES[n][:60]
        print(f"{n:2d}  page={p:3d}  [{src:4s}]  {title}")

    out = "/tmp/makarychev7_pages.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({str(k): pages[k] for k in sorted(pages)}, f, indent=2)
    print(f"\nSaved: {out}")

    print("\n# Paste into insert_toc_makarychev7.py PARAGRAPHS:")
    for n in range(1, 47):
        t = TITLES[n]
        print(f'    ({n:2d}, "{t}", {pages[n]}),')
    return 0


if __name__ == "__main__":
    sys.exit(main())
