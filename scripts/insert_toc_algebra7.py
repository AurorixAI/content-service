#!/usr/bin/env python3
"""
Вставляет полный TOC для «Алгебра 7 класс» (Узбекистан, Новое издательство, 2022).

Нумерация: упражнения в каждом параграфе начинаются с 1 (per-section).
Глобальные ключи параграфов: 0=Повторение-нач, 1-15=Гл1, 16-21=Гл2,
  22-25=Гл3, 26-29=Гл4, 30-32=Гл5, 33-35=Гл6, 36-38=Гл7, 39=Повторение-кон.

Использование: python3 /app/scripts/insert_toc_algebra7.py
"""
import sys
sys.path.insert(0, "/app")

from src.pipeline.db_writer import DBWriter

TEXTBOOK_ID = "4b19752a-3d54-4538-b6a6-26ce1fbb48fd"

TOC = [
    # ── ПОВТОРЕНИЕ (начало) ─────────────────────────────────────────────────
    {"level": 2, "number": "0",   "title": "Повторение пройденного в 6 классе", "page_start": 6,  "page_end": 11,  "sort_order": 0},

    # ── ГЛАВА 1. АЛГЕБРАИЧЕСКИЕ ВЫРАЖЕНИЯ И СТЕПЕНЬ ─────────────────────────
    {"level": 1, "number": "Г1",  "title": "Глава 1. Алгебраические выражения и степень",            "page_start": 12, "sort_order": 10},
    {"level": 2, "number": "1",   "title": "1. Числовые выражения",                                   "page_start": 12, "page_end": 14,  "sort_order": 11, "parent_number": "Г1"},
    {"level": 2, "number": "2",   "title": "2. Алгебраические выражения",                             "page_start": 15, "page_end": 16,  "sort_order": 12, "parent_number": "Г1"},
    {"level": 2, "number": "3",   "title": "3. Алгебраические равенства, формулы",                    "page_start": 17, "page_end": 19,  "sort_order": 13, "parent_number": "Г1"},
    {"level": 2, "number": "4",   "title": "4. Правила раскрытия скобок, коэффициент",                "page_start": 20, "page_end": 22,  "sort_order": 14, "parent_number": "Г1"},
    {"level": 2, "number": "5",   "title": "5. Свойства арифметических действий",                     "page_start": 23, "page_end": 25,  "sort_order": 15, "parent_number": "Г1"},
    {"level": 2, "number": "6",   "title": "6. Степень с натуральным показателем",                    "page_start": 26, "page_end": 29,  "sort_order": 16, "parent_number": "Г1"},
    {"level": 2, "number": "7",   "title": "7. Свойства степени с натуральным показателем",           "page_start": 30, "page_end": 33,  "sort_order": 17, "parent_number": "Г1"},
    {"level": 2, "number": "8",   "title": "8. Одночлен и его стандартный вид",                       "page_start": 34, "page_end": 35,  "sort_order": 18, "parent_number": "Г1"},
    {"level": 2, "number": "9",   "title": "9. Умножение и деление одночленов",                       "page_start": 36, "page_end": 37,  "sort_order": 19, "parent_number": "Г1"},
    {"level": 2, "number": "10",  "title": "10. Многочлены",                                          "page_start": 38, "page_end": 40,  "sort_order": 20, "parent_number": "Г1"},
    {"level": 2, "number": "11",  "title": "11. Подобные члены и их приведение",                      "page_start": 41, "page_end": 43,  "sort_order": 21, "parent_number": "Г1"},
    {"level": 2, "number": "12",  "title": "12. Сложение и вычитание многочленов",                    "page_start": 44, "page_end": 45,  "sort_order": 22, "parent_number": "Г1"},
    {"level": 2, "number": "13",  "title": "13. Умножение многочленов",                               "page_start": 46, "page_end": 49,  "sort_order": 23, "parent_number": "Г1"},
    {"level": 2, "number": "14",  "title": "14. Деление многочленов",                                 "page_start": 50, "page_end": 51,  "sort_order": 24, "parent_number": "Г1"},
    {"level": 2, "number": "15",  "title": "15. Разложение многочленов на множители",                 "page_start": 52, "page_end": 55,  "sort_order": 25, "parent_number": "Г1"},

    # ── ГЛАВА 2. ФОРМУЛЫ СОКРАЩЁННОГО УМНОЖЕНИЯ ─────────────────────────────
    {"level": 1, "number": "Г2",  "title": "Глава 2. Формулы сокращённого умножения",                 "page_start": 57, "sort_order": 30},
    {"level": 2, "number": "16",  "title": "1. Квадрат суммы и разности",                             "page_start": 57, "page_end": 59,  "sort_order": 31, "parent_number": "Г2"},
    {"level": 2, "number": "17",  "title": "2. Разность квадратов",                                   "page_start": 60, "page_end": 62,  "sort_order": 32, "parent_number": "Г2"},
    {"level": 2, "number": "18",  "title": "3. Куб суммы",                                            "page_start": 63, "page_end": 65,  "sort_order": 33, "parent_number": "Г2"},
    {"level": 2, "number": "19",  "title": "4. Разность и сумма кубов",                               "page_start": 66, "page_end": 68,  "sort_order": 34, "parent_number": "Г2"},
    {"level": 2, "number": "20",  "title": "5. Способы разложения на множители",                      "page_start": 69, "page_end": 70,  "sort_order": 35, "parent_number": "Г2"},
    {"level": 2, "number": "21",  "title": "6. Применение формул сокращённого умножения",             "page_start": 71, "page_end": 74,  "sort_order": 36, "parent_number": "Г2"},

    # ── ГЛАВА 3. АЛГЕБРАИЧЕСКИЕ ДРОБИ ───────────────────────────────────────
    {"level": 1, "number": "Г3",  "title": "Глава 3. Алгебраические дроби",                           "page_start": 75, "sort_order": 40},
    {"level": 2, "number": "22",  "title": "1. Алгебраическая дробь. Сокращение дробей",              "page_start": 75, "page_end": 79,  "sort_order": 41, "parent_number": "Г3"},
    {"level": 2, "number": "23",  "title": "2. Приведение алгебраических дробей к общему знаменателю","page_start": 80, "page_end": 82,  "sort_order": 42, "parent_number": "Г3"},
    {"level": 2, "number": "24",  "title": "3. Сложение и вычитание алгебраических дробей",           "page_start": 83, "page_end": 86,  "sort_order": 43, "parent_number": "Г3"},
    {"level": 2, "number": "25",  "title": "4. Умножение и деление алгебраических дробей",            "page_start": 87, "page_end": 92,  "sort_order": 44, "parent_number": "Г3"},

    # ── ГЛАВА 4. ЛИНЕЙНЫЕ УРАВНЕНИЯ ─────────────────────────────────────────
    {"level": 1, "number": "Г4",  "title": "Глава 4. Линейные уравнения",                             "page_start": 95, "sort_order": 50},
    {"level": 2, "number": "26",  "title": "1. Уравнение и его корень",                               "page_start": 95, "page_end": 96,  "sort_order": 51, "parent_number": "Г4"},
    {"level": 2, "number": "27",  "title": "2. Линейные уравнения с одним неизвестным",               "page_start": 97, "page_end": 100, "sort_order": 52, "parent_number": "Г4"},
    {"level": 2, "number": "28",  "title": "3. Способ решения уравнений аль-Хорезми",                 "page_start": 101,"page_end": 103, "sort_order": 53, "parent_number": "Г4"},
    {"level": 2, "number": "29",  "title": "4. Решение задач с помощью уравнений",                    "page_start": 104,"page_end": 111, "sort_order": 54, "parent_number": "Г4"},

    # ── ГЛАВА 5. ЛИНЕЙНАЯ ФУНКЦИЯ ────────────────────────────────────────────
    {"level": 1, "number": "Г5",  "title": "Глава 5. Линейная функция",                               "page_start": 112,"sort_order": 60},
    {"level": 2, "number": "30",  "title": "1. Декартова система координат",                          "page_start": 112,"page_end": 114, "sort_order": 61, "parent_number": "Г5"},
    {"level": 2, "number": "31",  "title": "2. Понятие функции",                                      "page_start": 115,"page_end": 119, "sort_order": 62, "parent_number": "Г5"},
    {"level": 2, "number": "32",  "title": "3. Линейная функция",                                     "page_start": 120,"page_end": 127, "sort_order": 63, "parent_number": "Г5"},

    # ── ГЛАВА 6. СИСТЕМЫ ЛИНЕЙНЫХ УРАВНЕНИЙ ─────────────────────────────────
    {"level": 1, "number": "Г6",  "title": "Глава 6. Системы линейных уравнений",                     "page_start": 131,"sort_order": 70},
    {"level": 2, "number": "33",  "title": "1. Системы линейных уравнений",                           "page_start": 131,"page_end": 136, "sort_order": 71, "parent_number": "Г6"},
    {"level": 2, "number": "34",  "title": "2. Способы решения систем линейных уравнений",            "page_start": 137,"page_end": 142, "sort_order": 72, "parent_number": "Г6"},
    {"level": 2, "number": "35",  "title": "3. Решение задач с помощью систем уравнений",             "page_start": 143,"page_end": 145, "sort_order": 73, "parent_number": "Г6"},

    # ── ГЛАВА 7. РАБОТА С ДАННЫМИ ────────────────────────────────────────────
    {"level": 1, "number": "Г7",  "title": "Глава 7. Работа с данными",                               "page_start": 146,"sort_order": 80},
    {"level": 2, "number": "36",  "title": "1. Основные правила комбинаторики",                       "page_start": 146,"page_end": 149, "sort_order": 81, "parent_number": "Г7"},
    {"level": 2, "number": "37",  "title": "2. Виды комбинаторных задач",                             "page_start": 150,"page_end": 155, "sort_order": 82, "parent_number": "Г7"},
    {"level": 2, "number": "38",  "title": "3. Способы решения комбинаторных задач",                  "page_start": 156,"page_end": 159, "sort_order": 83, "parent_number": "Г7"},

    # ── ПОВТОРЕНИЕ (итоговое) ────────────────────────────────────────────────
    {"level": 2, "number": "39",  "title": "Повторение",                                              "page_start": 160,"page_end": 172, "sort_order": 90},
]


def main():
    print(f"[algebra7_toc] Textbook: {TEXTBOOK_ID}")
    writer = DBWriter()
    count = writer.write_toc(TEXTBOOK_ID, TOC)
    print(f"[algebra7_toc] Done: {count} entries written to DB")


if __name__ == "__main__":
    main()
