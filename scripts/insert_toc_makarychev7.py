#!/usr/bin/env python3
"""
TOC Макарычев «Алгebра 7 класс» (Просвещение, 15-е изд. 2023, 257 с.).

Структура: level=1 глава, level=2 параграф (1–46) — leaf nodes для пайплайна.
Страницы верифицированы по OCR кэшу + оглавление издания 2023.

Usage:
    docker exec content-worker python /app/scripts/insert_toc_makarychev7.py [textbook_id]
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from src.core.config import get_settings
from src.pipeline.makarychev7_exercise_ranges import MAKARYCHEV7_PAGE_END_OVERRIDE

TEXTBOOK_ID = sys.argv[1] if len(sys.argv) > 1 else "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f"

# page_start для параграфов 1–46 (Макарычев 2023)
# §1–4: OCR; §5–46: верифицировано вручную по учебнику
PARAGRAPHS = [
    (1,  "Рациональные числа", 5),
    (2,  "Числовые выражения", 11),
    (3,  "Выражения с переменными", 14),
    (4,  "Сравнение значений выражений", 19),
    (5,  "Свойства действий над числами", 23),
    (6,  "Тождества. Тождественные преобразования выражений", 26),
    (7,  "Уравнение и его корни", 32),
    (8,  "Линейное уравнение с одной переменной", 34),
    (9,  "Решение задач с помощью уравнений", 38),
    (10, "Формулы", 42),
    (11, "Числовые промежутки", 51),
    (12, "Что такое функция", 54),
    (13, "Вычисление значений функции по формуле", 58),
    (14, "График функции", 61),
    (15, "Прямая пропорциональность и её график", 69),
    (16, "Линейная функция и её график", 74),
    (17, "Кусочно-заданные функции", 83),
    (18, "Определение степени с натуральным показателем", 95),
    (19, "Умножение и деление степеней", 101),
    (20, "Возведение в степень произведения и степени", 105),
    (21, "Одночлен и его стандартный вид", 110),
    (22, "Умножение одночленов. Возведение одночлена в степень", 112),
    (23, "Функции y = x² и y = x³ и их графики", 114),
    (24, "О простых и составных числах", 121),
    (25, "Многочлен и его стандартный вид", 129),
    (26, "Сложение и вычитание многочленов", 132),
    (27, "Умножение одночлена на многочлен", 137),
    (28, "Вынесение общего множителя за скобки", 142),
    (29, "Умножение многочлена на многочлен", 147),
    (30, "Разложение многочлена на множители способом группировки", 152),
    (31, "Деление с остатком", 154),
    (32, "Возведение в квадрат и в куб суммы и разности", 165),
    (33, "Разложение на множители (квадрат суммы и разности)", 171),
    (34, "Умножение разности на сумму", 174),
    (35, "Разложение разности квадратов на множители", 179),
    (36, "Разложение на множители суммы и разности кубов", 182),
    (37, "Преобразование целого выражения в многочлен", 185),
    (38, "Применение различных способов разложения на множители", 188),
    (39, "Возведение двучлена в степень", 192),
    (40, "Линейное уравнение с двумя переменными", 201),
    (41, "График линейного уравнения с двумя переменными", 206),
    (42, "Системы линейных уравнений с двумя переменными", 209),
    (43, "Способ подстановки", 213),
    (44, "Способ сложения", 217),
    (45, "Решение задач с помощью систем уравнений", 221),
    (46, "Линейные неравенства с двумя переменными и их системы", 225),
]

CHAPTERS = [
    ("I",   "ВЫРАЖЕНИЯ, ТОЖДЕСТВА, УРАВНЕНИЯ", 5,   range(1, 11)),
    ("II",  "ФУНКЦИИ", 51,  range(11, 18)),
    ("III", "СТЕПЕНЬ С НАТУРАЛЬНЫМ ПОКАЗАТЕЛЕМ", 95,  range(18, 25)),
    ("IV",  "МНОГОЧЛЕНЫ", 129, range(25, 32)),
    ("V",   "ФОРМУЛЫ СОКРАЩЁННОГО УМНОЖЕНИЯ", 165, range(32, 40)),
    ("VI",  "СИСТЕМЫ ЛИНЕЙНЫХ УРАВНЕНИЙ", 201, range(40, 47)),
]

PARA_PAGES = {n: p for n, _, p in PARAGRAPHS}


def _page_end(pnum: int) -> int | None:
    if pnum in MAKARYCHEV7_PAGE_END_OVERRIDE:
        return MAKARYCHEV7_PAGE_END_OVERRIDE[pnum]
    nxt = PARA_PAGES.get(pnum + 1)
    if nxt is not None:
        return nxt - 1
    return None


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    para_map = {n: (t, p) for n, t, p in PARAGRAPHS}

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM textbook_toc WHERE textbook_id = :tid"),
            {"tid": TEXTBOOK_ID},
        )

        chapter_ids: dict[str, int] = {}
        count = 0
        sort_order = 0

        for ch_num, ch_title, ch_page, para_range in CHAPTERS:
            row = conn.execute(
                text("""
                    INSERT INTO textbook_toc
                      (textbook_id, number, title, level, parent_id,
                       page_start, page_end, sort_order)
                    VALUES (:tid, :number, :title, 1, NULL,
                            :page_start, NULL, :sort_order)
                    RETURNING id
                """),
                {
                    "tid": TEXTBOOK_ID,
                    "number": f"Глава {ch_num}",
                    "title": ch_title,
                    "page_start": ch_page,
                    "sort_order": sort_order,
                },
            ).fetchone()
            chapter_ids[ch_num] = row[0]
            count += 1
            sort_order += 1

            for pnum in para_range:
                title, page = para_map[pnum]
                conn.execute(
                    text("""
                        INSERT INTO textbook_toc
                          (textbook_id, number, title, level, parent_id,
                           page_start, page_end, sort_order)
                        VALUES (:tid, :number, :title, 2, :parent_id,
                                :page_start, :page_end, :sort_order)
                    """),
                    {
                        "tid": TEXTBOOK_ID,
                        "number": str(pnum),
                        "title": title,
                        "parent_id": chapter_ids[ch_num],
                        "page_start": page,
                        "page_end": _page_end(pnum),
                        "sort_order": sort_order,
                    },
                )
                count += 1
                sort_order += 1

        conn.execute(
            text("""
                UPDATE textbooks
                SET total_pages = 257,
                    digitization_status = 'pending',
                    digitization_progress = 0,
                    tasks_extracted = 0,
                    figures_skipped = 0,
                    tasks_skipped = 0,
                    updated_at = NOW()
                WHERE textbook_id = :tid
            """),
            {"tid": TEXTBOOK_ID},
        )

    print(f"[TOC] Inserted {count} entries (6 chapters + 46 paragraphs) for {TEXTBOOK_ID}")

    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM textbook_toc WHERE textbook_id=:tid"),
            {"tid": TEXTBOOK_ID},
        ).scalar()
        leaves = conn.execute(
            text("""
                SELECT COUNT(*) FROM textbook_toc t
                WHERE textbook_id=:tid AND level=2
            """),
            {"tid": TEXTBOOK_ID},
        ).scalar()
    print(f"[TOC] Verified: {n} total, {leaves} leaf paragraphs")


if __name__ == "__main__":
    main()
