#!/usr/bin/env python3
"""Inserts Table of Contents for Alimov Algebra 9 (2019) into DB."""
from __future__ import annotations
import sys
import json

sys.path.insert(0, "/app")
from src.pipeline.db_writer import DBWriter

TEXTBOOK_ID = "2aa7af81-af13-42f9-a26b-e7e6bebaa4e6"

TOC = [
    # Вводная часть
    {"level": 2, "number": "Повт", "title": "Повторение тем, изученных в восьмом классе", "page_start": 3, "page_end": 4, "sort_order": 1},

    # ГЛАВА I
    {"level": 1, "number": "Г1", "title": "Глава I. КВАДРАТИЧНАЯ ФУНКЦИЯ. КВАДРАТНЫЕ НЕРАВЕНСТВА", "page_start": 5, "sort_order": 2},
    {"level": 2, "number": "1", "title": "§1. Определение квадратичной функции", "page_start": 5, "page_end": 6, "sort_order": 3, "parent_number": "Г1"},
    {"level": 2, "number": "2", "title": "§2. Функция y = x^2", "page_start": 7, "page_end": 9, "sort_order": 4, "parent_number": "Г1"},
    {"level": 2, "number": "3", "title": "§3. Функция y = ax^2", "page_start": 10, "page_end": 13, "sort_order": 5, "parent_number": "Г1"},
    {"level": 2, "number": "4", "title": "§4. Функция y = ax^2 + bx + c", "page_start": 14, "page_end": 17, "sort_order": 6, "parent_number": "Г1"},
    {"level": 2, "number": "5", "title": "§5. Построение графика квадратичной функции", "page_start": 18, "page_end": 23, "sort_order": 7, "parent_number": "Г1"},
    {"level": 2, "number": "6", "title": "§6. Квадратное неравенство и его решение", "page_start": 24, "page_end": 27, "sort_order": 8, "parent_number": "Г1"},
    {"level": 2, "number": "7", "title": "§7. Решение квадратного неравенства с помощью графика квадратичной функции", "page_start": 28, "page_end": 31, "sort_order": 9, "parent_number": "Г1"},
    {"level": 2, "number": "8", "title": "§8. Метод интервалов", "page_start": 32, "page_end": 36, "sort_order": 10, "parent_number": "Г1"},
    {"level": 2, "number": "9", "title": "§9. Область определения функции", "page_start": 37, "page_end": 40, "sort_order": 11, "parent_number": "Г1"},
    {"level": 2, "number": "10", "title": "§10. Возрастание и убывание функции", "page_start": 41, "page_end": 45, "sort_order": 12, "parent_number": "Г1"},
    {"level": 2, "number": "11", "title": "§11. Четность и нечетность функции", "page_start": 46, "page_end": 50, "sort_order": 13, "parent_number": "Г1"},
    {"level": 2, "number": "12", "title": "§12. Неравенства и уравнения, содержащие степень", "page_start": 51, "page_end": 55, "sort_order": 14, "parent_number": "Г1"},
    {"level": 2, "number": "УКГ1", "title": "Упражнения к главе I", "page_start": 56, "page_end": 59, "sort_order": 15, "parent_number": "Г1"},
    {"level": 2, "number": "ТЗГ1", "title": "Тестовые задания к главе I", "page_start": 60, "page_end": 62, "sort_order": 16, "parent_number": "Г1"},
    {"level": 2, "number": "ПМЗГ1", "title": "Практические и межпредметные задачи к главе I", "page_start": 63, "page_end": 66, "sort_order": 17, "parent_number": "Г1"},
    {"level": 2, "number": "ИСГ1", "title": "Исторические сведения к главе I", "page_start": 67, "page_end": 67, "sort_order": 18, "parent_number": "Г1"},

    # ГЛАВА II
    {"level": 1, "number": "Г2", "title": "Глава II. СИСТЕМЫ УРАВНЕНИЙ И НЕРАВЕНСТВ", "page_start": 68, "sort_order": 20},
    {"level": 2, "number": "13", "title": "§13. Решение простейших систем, содержащих уравнения второй степени", "page_start": 68, "page_end": 71, "sort_order": 21, "parent_number": "Г2"},
    {"level": 2, "number": "14", "title": "§14. Различные способы решения систем уравнений", "page_start": 72, "page_end": 76, "sort_order": 22, "parent_number": "Г2"},
    {"level": 2, "number": "15", "title": "§15. Система неравенств второй степени с одним неизвестным", "page_start": 77, "page_end": 79, "sort_order": 23, "parent_number": "Г2"},
    {"level": 2, "number": "16", "title": "§16. Доказательство простейших неравенств", "page_start": 80, "page_end": 83, "sort_order": 24, "parent_number": "Г2"},
    {"level": 2, "number": "УКГ2", "title": "Упражнения к главе II", "page_start": 84, "page_end": 86, "sort_order": 25, "parent_number": "Г2"},
    {"level": 2, "number": "ТЗГ2", "title": "Тестовые задания к главе II", "page_start": 87, "page_end": 88, "sort_order": 26, "parent_number": "Г2"},
    {"level": 2, "number": "ПМЗГ2", "title": "Практические и межпредметные задачи к главе II", "page_start": 89, "page_end": 92, "sort_order": 27, "parent_number": "Г2"},

    # ГЛАВА III
    {"level": 1, "number": "Г3", "title": "Глава III. ЭЛЕМЕНТЫ ТРИГОНОМЕТРИИ", "page_start": 93, "sort_order": 30},
    {"level": 2, "number": "17", "title": "§17. Радианная мера угла", "page_start": 93, "page_end": 96, "sort_order": 31, "parent_number": "Г3"},
    {"level": 2, "number": "18", "title": "§18. Поворот точки вокруг начала координат", "page_start": 97, "page_end": 102, "sort_order": 32, "parent_number": "Г3"},
    {"level": 2, "number": "19", "title": "§19. Определение синуса, косинуса, тангенса и котангенса угла", "page_start": 103, "page_end": 108, "sort_order": 33, "parent_number": "Г3"},
    {"level": 2, "number": "20", "title": "§20. Знаки синуса, косинуса и тангенса", "page_start": 109, "page_end": 111, "sort_order": 34, "parent_number": "Г3"},
    {"level": 2, "number": "21", "title": "§21. Зависимость между синусом, косинусом и тангенсом одного и того же угла", "page_start": 112, "page_end": 116, "sort_order": 35, "parent_number": "Г3"},
    {"level": 2, "number": "22", "title": "§22. Тригонометрические тождества", "page_start": 117, "page_end": 119, "sort_order": 36, "parent_number": "Г3"},
    {"level": 2, "number": "23", "title": "§23. Синус, косинус, тангенс и котангенс углов α и –α", "page_start": 120, "page_end": 120, "sort_order": 37, "parent_number": "Г3"},
    {"level": 2, "number": "24", "title": "§24. Формулы сложения", "page_start": 121, "page_end": 125, "sort_order": 38, "parent_number": "Г3"},
    {"level": 2, "number": "25", "title": "§25. Синус и косинус двойного угла", "page_start": 126, "page_end": 128, "sort_order": 39, "parent_number": "Г3"},
    {"level": 2, "number": "26", "title": "§26. Формулы приведения", "page_start": 129, "page_end": 134, "sort_order": 40, "parent_number": "Г3"},
    {"level": 2, "number": "27", "title": "§27. Сумма и разность синусов. Сумма и разность косинусов", "page_start": 135, "page_end": 137, "sort_order": 41, "parent_number": "Г3"},
    {"level": 2, "number": "УКГ3", "title": "Упражнения к главе III", "page_start": 138, "page_end": 141, "sort_order": 42, "parent_number": "Г3"},
    {"level": 2, "number": "ТЗГ3", "title": "Тестовые задания к главе III", "page_start": 142, "page_end": 144, "sort_order": 43, "parent_number": "Г3"},
    {"level": 2, "number": "ПМЗГ3", "title": "Практические и межпредметные задачи к главе III", "page_start": 145, "page_end": 147, "sort_order": 44, "parent_number": "Г3"},
    {"level": 2, "number": "ИЗГ3", "title": "Исторические задачи к главе III", "page_start": 148, "page_end": 148, "sort_order": 45, "parent_number": "Г3"},
    {"level": 2, "number": "ИСГ3", "title": "Исторические сведения к главе III", "page_start": 149, "page_end": 149, "sort_order": 46, "parent_number": "Г3"},

    # ГЛАВА IV
    {"level": 1, "number": "Г4", "title": "Глава IV. ЧИСЛОВЫЕ ПОСЛЕДОВАТЕЛЬНОСТИ. ПРОГРЕССИИ", "page_start": 150, "sort_order": 50},
    {"level": 2, "number": "28", "title": "§28. Числовые последовательности", "page_start": 150, "page_end": 152, "sort_order": 51, "parent_number": "Г4"},
    {"level": 2, "number": "29", "title": "§29. Арифметическая прогрессия", "page_start": 153, "page_end": 157, "sort_order": 52, "parent_number": "Г4"},
    {"level": 2, "number": "30", "title": "§30. Сумма n первых членов арифметической прогрессии", "page_start": 158, "page_end": 161, "sort_order": 53, "parent_number": "Г4"},
    {"level": 2, "number": "31", "title": "§31. Геометрическая прогрессия", "page_start": 162, "page_end": 165, "sort_order": 54, "parent_number": "Г4"},
    {"level": 2, "number": "32", "title": "§32. Сумма n первых членов геометрической прогрессии", "page_start": 167, "page_end": 170, "sort_order": 55, "parent_number": "Г4"},
    {"level": 2, "number": "33", "title": "§33. Бесконечно убывающая геометрическая прогрессия", "page_start": 171, "page_end": 176, "sort_order": 56, "parent_number": "Г4"},
    {"level": 2, "number": "УКГ4", "title": "Упражнения к главе IV", "page_start": 177, "page_end": 179, "sort_order": 57, "parent_number": "Г4"},
    {"level": 2, "number": "ТЗГ4", "title": "Тестовые задания к главе IV", "page_start": 180, "page_end": 181, "sort_order": 58, "parent_number": "Г4"},
    {"level": 2, "number": "ПМЗГ4", "title": "Практические и межпредметные задачи к главе IV", "page_start": 182, "page_end": 185, "sort_order": 59, "parent_number": "Г4"},

    # ГЛАВА V
    {"level": 1, "number": "Г5", "title": "Глава V. ТЕОРИЯ ВЕРОЯТНОСТЕЙ И МАТЕМАТИЧЕСКАЯ СТАТИСТИКА", "page_start": 186, "sort_order": 60},
    {"level": 2, "number": "34", "title": "§34. События", "page_start": 186, "page_end": 189, "sort_order": 61, "parent_number": "Г5"},
    {"level": 2, "number": "35", "title": "§35. Вероятность события", "page_start": 190, "page_end": 193, "sort_order": 62, "parent_number": "Г5"},
    {"level": 2, "number": "36", "title": "§36. Относительная частота случайного события", "page_start": 194, "page_end": 197, "sort_order": 63, "parent_number": "Г5"},
    {"level": 2, "number": "37", "title": "§37. Случайные величины", "page_start": 198, "page_end": 205, "sort_order": 64, "parent_number": "Г5"},
    {"level": 2, "number": "38", "title": "§38. Числовые характеристики случайных величин", "page_start": 206, "page_end": 212, "sort_order": 65, "parent_number": "Г5"},
    {"level": 2, "number": "УКГ5", "title": "Упражнения к главе V", "page_start": 213, "page_end": 213, "sort_order": 66, "parent_number": "Г5"},
    {"level": 2, "number": "ТЗГ5", "title": "Тестовые задания к главе V", "page_start": 214, "page_end": 215, "sort_order": 67, "parent_number": "Г5"},
    {"level": 2, "number": "ПМЗГ5", "title": "Практические и межпредметные задачи к главе V", "page_start": 216, "page_end": 221, "sort_order": 68, "parent_number": "Г5"},

    # Итоговые разделы
    {"level": 2, "number": "ПовтКурс", "title": "Упражнения для повторения курса «Алгебры» 9 класса", "page_start": 222, "page_end": 240, "sort_order": 70}
]

# Set page_end of items if not explicitly set
for i in range(len(TOC)):
    if "page_end" not in TOC[i]:
        # find next item with page_start
        next_start = 240
        for j in range(i + 1, len(TOC)):
            if TOC[j].get("page_start"):
                next_start = TOC[j]["page_start"]
                break
        TOC[i]["page_end"] = next_start - 1

def main() -> int:
    print(f"Ingesting TOC for Alimov Algebra 9. Textbook ID: {TEXTBOOK_ID}")
    writer = DBWriter()
    n = writer.write_toc(TEXTBOOK_ID, TOC)
    print(f"Successfully inserted {n} TOC entries.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
