#!/usr/bin/env python3
"""
TOC «Алгebра 8 класс» (IDUM / O'qituvchi, 2019) — из оглавления стр. 236–241.

Нумерация параграфов: 0=Повторение 7 кл, 1–31=§1–§31, 32=Повторение 8 кл.
Упражнения в книге — сквозная нумерация (как Макарычев).

Usage:
    docker exec content-worker python /app/scripts/insert_toc_algebra8.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from src.pipeline.db_writer import DBWriter

TEXTBOOK_ID = "e8f3a1b2-7c4d-5e6f-8091-2345678abcde"

# page_end = next page_start - 1 (from OCR оглавления p.236–241)
TOC = [
    {"level": 2, "number": "0", "title": "Повторение курса «Алгебры» 7 класса", "page_start": 3, "page_end": 6, "sort_order": 0},

    {"level": 1, "number": "Г1", "title": "Глава I. Алгебраические дроби и действия над ними", "page_start": 7, "sort_order": 10},
    {"level": 2, "number": "1", "title": "§1. Алгебраические выражения", "page_start": 7, "page_end": 11, "sort_order": 11, "parent_number": "Г1"},
    {"level": 2, "number": "2", "title": "§2. Алгебраическая дробь. Сокращение дробей", "page_start": 12, "page_end": 17, "sort_order": 12, "parent_number": "Г1"},
    {"level": 2, "number": "3", "title": "§3. Приведение дробей к общему знаменателю", "page_start": 18, "page_end": 21, "sort_order": 13, "parent_number": "Г1"},
    {"level": 2, "number": "4", "title": "§4. Сложение и вычитание алгебраических дробей", "page_start": 22, "page_end": 26, "sort_order": 14, "parent_number": "Г1"},
    {"level": 2, "number": "5", "title": "§5. Умножение и деление алгебраических дробей", "page_start": 27, "page_end": 29, "sort_order": 15, "parent_number": "Г1"},
    {"level": 2, "number": "6", "title": "§6. Замена дробно-рациональных выражений тождественными", "page_start": 30, "page_end": 33, "sort_order": 16, "parent_number": "Г1"},
    {"level": 2, "number": "7", "title": "§7. Функция y = k/x. Ее свойства и график", "page_start": 34, "page_end": 38, "sort_order": 17, "parent_number": "Г1"},
    {"level": 2, "number": "8", "title": "§8. Арифметический корень натуральной степени и его свойства", "page_start": 39, "page_end": 41, "sort_order": 18, "parent_number": "Г1"},
    {"level": 2, "number": "9", "title": "§9. Степень с рациональным показателем и его свойства", "page_start": 42, "page_end": 48, "sort_order": 19, "parent_number": "Г1"},
    {"level": 2, "number": "10", "title": "§10. Упрощение выражений со степенью с рациональным показателем", "page_start": 49, "page_end": 67, "sort_order": 20, "parent_number": "Г1"},

    {"level": 1, "number": "Г2", "title": "Глава II. Неравенства", "page_start": 68, "sort_order": 30},
    {"level": 2, "number": "11", "title": "§11. Числовые неравенства", "page_start": 68, "page_end": 70, "sort_order": 31, "parent_number": "Г2"},
    {"level": 2, "number": "12", "title": "§12. Основные свойства числовых неравенств", "page_start": 71, "page_end": 74, "sort_order": 32, "parent_number": "Г2"},
    {"level": 2, "number": "13", "title": "§13. Сложение и умножение неравенств", "page_start": 75, "page_end": 79, "sort_order": 33, "parent_number": "Г2"},
    {"level": 2, "number": "14", "title": "§14. Возведение числовых неравенств в степень", "page_start": 80, "page_end": 84, "sort_order": 34, "parent_number": "Г2"},
    {"level": 2, "number": "15", "title": "§15. Неравенство с одним неизвестным", "page_start": 85, "page_end": 93, "sort_order": 35, "parent_number": "Г2"},
    {"level": 2, "number": "16", "title": "§16. Системы неравенств с одним неизвестным. Числовые промежутки", "page_start": 94, "page_end": 104, "sort_order": 36, "parent_number": "Г2"},
    {"level": 2, "number": "17", "title": "§17. Модуль числа. Уравнения и неравенства с модулем", "page_start": 105, "page_end": 110, "sort_order": 37, "parent_number": "Г2"},
    {"level": 2, "number": "18", "title": "§18. Приближённые вычисления. Погрешность приближения", "page_start": 111, "page_end": 113, "sort_order": 38, "parent_number": "Г2"},
    {"level": 2, "number": "19", "title": "§19. Оценка погрешностей", "page_start": 114, "page_end": 116, "sort_order": 39, "parent_number": "Г2"},
    {"level": 2, "number": "20", "title": "§20. Округление чисел", "page_start": 117, "page_end": 118, "sort_order": 40, "parent_number": "Г2"},
    {"level": 2, "number": "21", "title": "§21. Относительная погрешность", "page_start": 119, "page_end": 134, "sort_order": 41, "parent_number": "Г2"},

    {"level": 1, "number": "Г3", "title": "Глава III. Квадратные уравнения", "page_start": 135, "sort_order": 50},
    {"level": 2, "number": "22", "title": "§22. Квадратные уравнения и их корни", "page_start": 135, "page_end": 138, "sort_order": 51, "parent_number": "Г3"},
    {"level": 2, "number": "23", "title": "§23. Неполные квадратные уравнения и их решение", "page_start": 139, "page_end": 140, "sort_order": 52, "parent_number": "Г3"},
    {"level": 2, "number": "24", "title": "§24. Формулы корней квадратного уравнения. Дискриминант", "page_start": 141, "page_end": 148, "sort_order": 53, "parent_number": "Г3"},
    {"level": 2, "number": "25", "title": "§25. Теорема Виета. Разложение квадратного трёхчлена", "page_start": 149, "page_end": 155, "sort_order": 54, "parent_number": "Г3"},
    {"level": 2, "number": "26", "title": "§26. Биквадратные уравнения. Уравнения, сводящиеся к квадратным", "page_start": 156, "page_end": 162, "sort_order": 55, "parent_number": "Г3"},
    {"level": 2, "number": "27", "title": "§27. Решение задач с помощью квадратных уравнений", "page_start": 163, "page_end": 187, "sort_order": 56, "parent_number": "Г3"},

    {"level": 1, "number": "Г4", "title": "Глава IV. Анализ данных", "page_start": 188, "sort_order": 60},
    {"level": 2, "number": "28", "title": "§28. Анализ данных. Представление данных", "page_start": 188, "page_end": 192, "sort_order": 61, "parent_number": "Г4"},
    {"level": 2, "number": "29", "title": "§29. Среднее значение. Мода. Медиана", "page_start": 193, "page_end": 199, "sort_order": 62, "parent_number": "Г4"},
    {"level": 2, "number": "30", "title": "§30. Решение комбинаторных задач методом перебора", "page_start": 200, "page_end": 202, "sort_order": 63, "parent_number": "Г4"},
    {"level": 2, "number": "31", "title": "§31. Основной закон комбинаторики и его применение", "page_start": 203, "page_end": 218, "sort_order": 64, "parent_number": "Г4"},

    {"level": 1, "number": "Г5", "title": "Глава V. Повторение", "page_start": 219, "sort_order": 70},
    {"level": 2, "number": "32", "title": "Упражнения для повторения курса «Алгебры» 8 класса", "page_start": 219, "page_end": 226, "sort_order": 71, "parent_number": "Г5"},
]


def main() -> int:
    print(f"[algebra8_toc] Textbook: {TEXTBOOK_ID}")
    writer = DBWriter()
    n = writer.write_toc(TEXTBOOK_ID, TOC)
    print(f"[algebra8_toc] Done: {n} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
