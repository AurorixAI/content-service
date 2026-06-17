#!/usr/bin/env python3
"""Extract exact paragraph start pages from OCR pipeline cache (Makarychev G7).

Reads cached gemini_*.md batches, finds `### N. Title` / `## N. Title` headers
and footer page numbers (`§ ...  42`, `**42**`, trailing digit).

Usage:
    docker exec content-worker python /app/scripts/parse_makarychev7_pages_from_cache.py
"""
from __future__ import annotations

import glob
import json
import re
import sys

sys.path.insert(0, "/app")

import fitz

PDF = "/textbooks/7_grade/1701411287_algebra_-uchebnik_-7-kl_-makarychev_compressed.pdf"
CACHE_GLOB = "/tmp/content_pipeline_cache/gemini_*_p*.md"

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

# § section → first paragraph number
SECTION_FIRST = {
    1: 1, 2: 5, 3: 7, 4: 11, 5: 15, 6: 18, 7: 21,
    8: 25, 9: 27, 10: 29, 11: 32, 12: 34, 13: 37, 14: 40, 15: 43,
}


def _page_from_chunk(chunk: str, batch_start: int) -> int | None:
    foot = re.findall(r"\*\*(\d{1,3})\*\*\s*$", chunk, re.M)
    foot += re.findall(r"\|\s*(\d{1,3})\s*$", chunk, re.M)
    foot += re.findall(r"§\s*\d+\.\s+[^\n]+\s+(\d{1,3})\s*$", chunk, re.M)
    foot += re.findall(r"^(\d{1,3})\s*$", chunk, re.M)
    if foot:
        p = int(foot[-1])
        if 1 <= p <= 300:
            return p
    return None


def _parse_cache() -> dict[int, int]:
    found: dict[int, int] = {}

    for path in sorted(glob.glob(CACHE_GLOB)):
        m = re.search(r"_p(\d+)-", path)
        batch_start = int(m.group(1)) if m else 1
        text = open(path, encoding="utf-8").read()
        chunks = re.split(r"---\s*страница\s*---", text, flags=re.I)

        for chunk in chunks:
            page = _page_from_chunk(chunk, batch_start)
            if page is None or page < 5:
                continue

            for mm in re.finditer(
                r"^#{1,3}\s*(\d{1,2})\.\s+([A-Za-zА-Яа-яЁё«].+)$", chunk, re.M
            ):
                num = int(mm.group(1))
                if 1 <= num <= 46:
                    if num not in found or page < found[num]:
                        found[num] = page

            for mm in re.finditer(r"^##\s*(\d{1,2})\.\s+(.+)$", chunk, re.M):
                num = int(mm.group(1))
                if 1 <= num <= 46:
                    if num not in found or page < found[num]:
                        found[num] = page

            for mm in re.finditer(r"^§\s*(\d{1,2})\.\s+", chunk, re.M):
                sec = int(mm.group(1))
                para = SECTION_FIRST.get(sec)
                if para and (para not in found or page < found[para]):
                    found[para] = page

    return found


def _fill_gaps(found: dict[int, int], total: int) -> dict[int, int]:
    pages = dict(found)
    for n in range(1, 47):
        if n not in pages:
            prev = next((pages[k] for k in range(n - 1, 0, -1) if k in pages), 5)
            nxt = next((pages[k] for k in range(n + 1, 47) if k in pages), total)
            pages[n] = min(prev + 1, max(prev + 1, nxt - 1))
        pages[n] = max(5, min(pages[n], total))
    for n in range(2, 47):
        if pages[n] <= pages[n - 1]:
            pages[n] = pages[n - 1] + 1
    return pages


def main() -> int:
    found = _parse_cache()
    total = fitz.open(PDF).page_count
    pages = _fill_gaps(found, total)

    print("=== PARAGRAPH PAGES (OCR cache) ===")
    ocr_count = 0
    for n in range(1, 47):
        src = "OCR" if n in found else "fill"
        if n in found:
            ocr_count += 1
        print(f"{n:2d}  page={pages[n]:3d}  [{src:4s}]  {TITLES[n][:50]}")

    print(f"\nOCR-detected: {ocr_count}/46")
    with open("/tmp/makarychev7_pages.json", "w", encoding="utf-8") as f:
        json.dump({str(k): pages[k] for k in sorted(pages)}, f, indent=2)

    print("\n# PARAGRAPHS for insert_toc_makarychev7.py:")
    for n in range(1, 47):
        print(f'    ({n:2d}, "{TITLES[n]}", {pages[n]}),')
    return 0


if __name__ == "__main__":
    sys.exit(main())
