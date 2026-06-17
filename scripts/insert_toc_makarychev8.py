#!/usr/bin/env python3
"""
TOC Макарычев «Алгебра 8 класс» (Просвещение, 2022, 321 с.).

Структура: level=1 глава, level=2 параграф (1–51) — leaf nodes для пайплайна.
Страницы верифицированы по оглавлению PDF стр. 318–320 (печатные 317–319).

Usage:
    docker exec content-worker python /app/scripts/insert_toc_makarychev8.py [textbook_id]
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from src.core.config import get_settings

TEXTBOOK_ID = sys.argv[1] if len(sys.argv) > 1 else "b8f4a2c1-3d5e-4f60-9182-3456789abcde"

# page_start из оглавления (печатные номера = PDF)
PARAGRAPHS = [
    (1,  "Рациональные выражения", 5),
    (2,  "Основное свойство дроби. Сокращение дробей", 10),
    (3,  "Сложение и вычитание дробей с одинаковыми знаменателями", 19),
    (4,  "Сложение и вычитание дробей с разными знаменателями", 23),
    (5,  "Умножение дробей. Возведение дроби в степень", 30),
    (6,  "Деление дробей", 35),
    (7,  "Преобразование рациональных выражений", 38),
    (8,  "Функция y = k/x и её график", 45),
    (9,  "Представление дроби в виде суммы дробей", 52),
    (10, "Действительные числа", 64),
    (11, "Квадратные корни. Арифметический квадратный корень", 70),
    (12, "Уравнение x² = a", 74),
    (13, "Нахождение приближённых значений квадратного корня", 78),
    (14, "Функция y = √x и её график", 81),
    (15, "Квадратный корень из произведения и дроби", 86),
    (16, "Квадратный корень из степени", 91),
    (17, "Вынесение множителя из-под знака корня. Внесение множителя под знак корня", 94),
    (18, "Преобразование выражений, содержащих квадратные корни", 98),
    (19, "Преобразование двойных радикалов", 103),
    (20, "Неполные квадратные уравнения", 115),
    (21, "Формула корней квадратного уравнения", 120),
    (22, "Решение задач", 128),
    (23, "Теорема Виета", 132),
    (24, "Квадратный трёхчлен и его корни", 137),
    (25, "Разложение квадратного трёхчлена на множители", 141),
    (26, "Решение дробных рациональных уравнений", 145),
    (27, "Решение задач", 151),
    (28, "Уравнение с двумя переменными и его график", 155),
    (29, "Исследование систем двух линейных уравнений с двумя переменными", 160),
    (30, "Графический способ решения систем уравнений", 163),
    (31, "Алгебраический способ решения систем уравнений", 165),
    (32, "Решение задач", 169),
    (33, "Уравнения с параметром", 172),
    (34, "Числовые неравенства", 185),
    (35, "Свойства числовых неравенств", 190),
    (36, "Сложение и умножение числовых неравенств", 195),
    (37, "Пересечение и объединение множеств", 200),
    (38, "Числовые промежутки", 203),
    (39, "Решение неравенств с одной переменной", 207),
    (40, "Решение систем неравенств с одной переменной", 215),
    (41, "Доказательство неравенств", 223),
    (42, "Функция. Область определения и множество значений функции", 234),
    (43, "Свойства функции", 243),
    (44, "Свойства линейной функции", 249),
    (45, "Свойства функций y = k/x и y = √x", 252),
    (46, "Целая и дробная части числа", 255),
    (47, "Определение степени с целым отрицательным показателем", 261),
    (48, "Свойства степени с целым показателем", 265),
    (49, "Понятие стандартного вида числа", 270),
    (50, "Решение задач с большими и малыми числами", 272),
    (51, "Функции y = x⁻¹ и y = x⁻² и их свойства", 275),
]

CHAPTERS = [
    ("I",   "РАЦИОНАЛЬНЫЕ ДРОБИ", 5,   range(1, 10)),
    ("II",  "КВАДРАТНЫЕ КОРНИ", 64,  range(10, 20)),
    ("III", "УРАВНЕНИЯ И СИСТЕМЫ УРАВНЕНИЙ", 115, range(20, 34)),
    ("IV",  "НЕРАВЕНСТВА", 185, range(34, 42)),
    ("V",   "ФУНКЦИИ", 234, range(42, 47)),
    ("VI",  "СТЕПЕНЬ С ЦЕЛЫМ ПОКАЗАТЕЛЕМ", 261, range(47, 52)),
]

PAGE_END_OVERRIDE = {51: 281}

PARA_PAGES = {n: p for n, _, p in PARAGRAPHS}


def _page_end(pnum: int) -> int | None:
    if pnum in PAGE_END_OVERRIDE:
        return PAGE_END_OVERRIDE[pnum]
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
                SET total_pages = 321,
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

    print(f"[TOC] Inserted {count} entries (6 chapters + 51 paragraphs) for {TEXTBOOK_ID}")

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
