#!/usr/bin/env python3
"""
Вставляет TOC Виленкина 6 класс напрямую в БД.
Структура соответствует изданию Мнемозина (стандартная для всех редакций).
"""
import sys
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from src.core.config import get_settings

TEXTBOOK_ID = sys.argv[1] if len(sys.argv) > 1 else "351a95c1-5208-4ae9-8323-6d7dd5e8bb82"

# TOC Виленкин Математика 6 класс (Мнемозина)
# Структура: level=1 — глава, level=2 — параграф
TOC = [
    # Глава 1
    {"number": "1", "title": "Делимость натуральных чисел", "level": 1, "parent_number": "", "page_start": 4, "page_end": None, "sort_order": 0},
    {"number": "1", "title": "Делители и кратные", "level": 2, "parent_number": "1", "page_start": 5, "page_end": None, "sort_order": 1},
    {"number": "2", "title": "Признаки делимости на 10, 5 и 2", "level": 2, "parent_number": "1", "page_start": 14, "page_end": None, "sort_order": 2},
    {"number": "3", "title": "Признаки делимости на 9 и 3", "level": 2, "parent_number": "1", "page_start": 19, "page_end": None, "sort_order": 3},
    {"number": "4", "title": "Простые и составные числа", "level": 2, "parent_number": "1", "page_start": 24, "page_end": None, "sort_order": 4},
    {"number": "5", "title": "Разложение на простые множители", "level": 2, "parent_number": "1", "page_start": 30, "page_end": None, "sort_order": 5},
    {"number": "6", "title": "Наибольший общий делитель. Взаимно простые числа", "level": 2, "parent_number": "1", "page_start": 35, "page_end": None, "sort_order": 6},
    {"number": "7", "title": "Наименьшее общее кратное", "level": 2, "parent_number": "1", "page_start": 42, "page_end": None, "sort_order": 7},

    # Глава 2
    {"number": "2", "title": "Сложение и вычитание дробей с разными знаменателями", "level": 1, "parent_number": "", "page_start": 52, "page_end": None, "sort_order": 8},
    {"number": "8", "title": "Основное свойство дроби", "level": 2, "parent_number": "2", "page_start": 53, "page_end": None, "sort_order": 9},
    {"number": "9", "title": "Сокращение дробей", "level": 2, "parent_number": "2", "page_start": 57, "page_end": None, "sort_order": 10},
    {"number": "10", "title": "Приведение дробей к общему знаменателю", "level": 2, "parent_number": "2", "page_start": 62, "page_end": None, "sort_order": 11},
    {"number": "11", "title": "Сравнение, сложение и вычитание дробей с разными знаменателями", "level": 2, "parent_number": "2", "page_start": 66, "page_end": None, "sort_order": 12},
    {"number": "12", "title": "Сложение и вычитание смешанных чисел", "level": 2, "parent_number": "2", "page_start": 74, "page_end": None, "sort_order": 13},

    # Глава 3
    {"number": "3", "title": "Умножение и деление обыкновенных дробей", "level": 1, "parent_number": "", "page_start": 88, "page_end": None, "sort_order": 14},
    {"number": "13", "title": "Умножение дробей", "level": 2, "parent_number": "3", "page_start": 89, "page_end": None, "sort_order": 15},
    {"number": "14", "title": "Нахождение дроби от числа", "level": 2, "parent_number": "3", "page_start": 95, "page_end": None, "sort_order": 16},
    {"number": "15", "title": "Применение распределительного свойства умножения", "level": 2, "parent_number": "3", "page_start": 101, "page_end": None, "sort_order": 17},
    {"number": "16", "title": "Взаимно обратные числа", "level": 2, "parent_number": "3", "page_start": 107, "page_end": None, "sort_order": 18},
    {"number": "17", "title": "Деление дробей", "level": 2, "parent_number": "3", "page_start": 110, "page_end": None, "sort_order": 19},
    {"number": "18", "title": "Нахождение числа по его дроби", "level": 2, "parent_number": "3", "page_start": 117, "page_end": None, "sort_order": 20},
    {"number": "19", "title": "Дробные выражения", "level": 2, "parent_number": "3", "page_start": 122, "page_end": None, "sort_order": 21},

    # Глава 4
    {"number": "4", "title": "Отношения и пропорции", "level": 1, "parent_number": "", "page_start": 133, "page_end": None, "sort_order": 22},
    {"number": "20", "title": "Отношения", "level": 2, "parent_number": "4", "page_start": 134, "page_end": None, "sort_order": 23},
    {"number": "21", "title": "Пропорции", "level": 2, "parent_number": "4", "page_start": 141, "page_end": None, "sort_order": 24},
    {"number": "22", "title": "Прямая и обратная пропорциональные зависимости", "level": 2, "parent_number": "4", "page_start": 148, "page_end": None, "sort_order": 25},
    {"number": "23", "title": "Масштаб", "level": 2, "parent_number": "4", "page_start": 155, "page_end": None, "sort_order": 26},
    {"number": "24", "title": "Длина окружности и площадь круга", "level": 2, "parent_number": "4", "page_start": 160, "page_end": None, "sort_order": 27},
    {"number": "25", "title": "Шар", "level": 2, "parent_number": "4", "page_start": 166, "page_end": None, "sort_order": 28},

    # Глава 5
    {"number": "5", "title": "Положительные и отрицательные числа", "level": 1, "parent_number": "", "page_start": 175, "page_end": None, "sort_order": 29},
    {"number": "26", "title": "Координаты на прямой", "level": 2, "parent_number": "5", "page_start": 176, "page_end": None, "sort_order": 30},
    {"number": "27", "title": "Противоположные числа", "level": 2, "parent_number": "5", "page_start": 183, "page_end": None, "sort_order": 31},
    {"number": "28", "title": "Модуль числа", "level": 2, "parent_number": "5", "page_start": 187, "page_end": None, "sort_order": 32},
    {"number": "29", "title": "Сравнение чисел", "level": 2, "parent_number": "5", "page_start": 191, "page_end": None, "sort_order": 33},
    {"number": "30", "title": "Изменение величин", "level": 2, "parent_number": "5", "page_start": 196, "page_end": None, "sort_order": 34},

    # Глава 6
    {"number": "6", "title": "Сложение и вычитание положительных и отрицательных чисел", "level": 1, "parent_number": "", "page_start": 201, "page_end": None, "sort_order": 35},
    {"number": "31", "title": "Сложение чисел с помощью координатной прямой", "level": 2, "parent_number": "6", "page_start": 202, "page_end": None, "sort_order": 36},
    {"number": "32", "title": "Сложение отрицательных чисел", "level": 2, "parent_number": "6", "page_start": 206, "page_end": None, "sort_order": 37},
    {"number": "33", "title": "Сложение чисел с разными знаками", "level": 2, "parent_number": "6", "page_start": 210, "page_end": None, "sort_order": 38},
    {"number": "34", "title": "Вычитание", "level": 2, "parent_number": "6", "page_start": 215, "page_end": None, "sort_order": 39},

    # Глава 7
    {"number": "7", "title": "Умножение и деление положительных и отрицательных чисел", "level": 1, "parent_number": "", "page_start": 224, "page_end": None, "sort_order": 40},
    {"number": "35", "title": "Умножение", "level": 2, "parent_number": "7", "page_start": 225, "page_end": None, "sort_order": 41},
    {"number": "36", "title": "Деление", "level": 2, "parent_number": "7", "page_start": 231, "page_end": None, "sort_order": 42},
    {"number": "37", "title": "Рациональные числа", "level": 2, "parent_number": "7", "page_start": 236, "page_end": None, "sort_order": 43},
    {"number": "38", "title": "Свойства действий с рациональными числами", "level": 2, "parent_number": "7", "page_start": 241, "page_end": None, "sort_order": 44},

    # Глава 8
    {"number": "8", "title": "Решение уравнений", "level": 1, "parent_number": "", "page_start": 248, "page_end": None, "sort_order": 45},
    {"number": "39", "title": "Раскрытие скобок", "level": 2, "parent_number": "8", "page_start": 249, "page_end": None, "sort_order": 46},
    {"number": "40", "title": "Коэффициент", "level": 2, "parent_number": "8", "page_start": 253, "page_end": None, "sort_order": 47},
    {"number": "41", "title": "Подобные слагаемые", "level": 2, "parent_number": "8", "page_start": 257, "page_end": None, "sort_order": 48},
    {"number": "42", "title": "Решение уравнений", "level": 2, "parent_number": "8", "page_start": 262, "page_end": None, "sort_order": 49},

    # Глава 9
    {"number": "9", "title": "Координаты на плоскости", "level": 1, "parent_number": "", "page_start": 268, "page_end": None, "sort_order": 50},
    {"number": "43", "title": "Перпендикулярные прямые", "level": 2, "parent_number": "9", "page_start": 269, "page_end": None, "sort_order": 51},
    {"number": "44", "title": "Параллельные прямые", "level": 2, "parent_number": "9", "page_start": 272, "page_end": None, "sort_order": 52},
    {"number": "45", "title": "Координатная плоскость", "level": 2, "parent_number": "9", "page_start": 276, "page_end": None, "sort_order": 53},
    {"number": "46", "title": "Столбчатые диаграммы", "level": 2, "parent_number": "9", "page_start": 281, "page_end": None, "sort_order": 54},
    {"number": "47", "title": "Графики", "level": 2, "parent_number": "9", "page_start": 284, "page_end": None, "sort_order": 55},
]

def main():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    
    with engine.begin() as conn:
        # Удаляем старый TOC если есть
        conn.execute(text("DELETE FROM textbook_toc WHERE textbook_id = :tid"), {"tid": TEXTBOOK_ID})
        
        # Шаг 1: вставляем записи верхнего уровня (level=1) и сохраняем их id
        chapter_ids: dict[str, int] = {}
        for entry in TOC:
            if entry["level"] != 1:
                continue
            row = conn.execute(text("""
                INSERT INTO textbook_toc
                  (textbook_id, number, title, level, parent_id,
                   page_start, page_end, sort_order)
                VALUES (:tid, :number, :title, :level, NULL,
                        :page_start, :page_end, :sort_order)
                RETURNING id
            """), {
                "tid": TEXTBOOK_ID,
                "number": entry["number"],
                "title": entry["title"],
                "level": entry["level"],
                "page_start": entry.get("page_start"),
                "page_end": entry.get("page_end"),
                "sort_order": entry["sort_order"],
            }).fetchone()
            chapter_ids[entry["number"]] = row[0]
        
        # Шаг 2: вставляем параграфы со ссылкой на родительскую главу
        count = len(chapter_ids)
        for entry in TOC:
            if entry["level"] == 1:
                continue
            parent_id = chapter_ids.get(entry["parent_number"])
            conn.execute(text("""
                INSERT INTO textbook_toc
                  (textbook_id, number, title, level, parent_id,
                   page_start, page_end, sort_order)
                VALUES (:tid, :number, :title, :level, :parent_id,
                        :page_start, :page_end, :sort_order)
            """), {
                "tid": TEXTBOOK_ID,
                "number": entry["number"],
                "title": entry["title"],
                "level": entry["level"],
                "parent_id": parent_id,
                "page_start": entry.get("page_start"),
                "page_end": entry.get("page_end"),
                "sort_order": entry["sort_order"],
            })
            count += 1
    
    print(f"[TOC] Inserted {count} entries for textbook {TEXTBOOK_ID}")
    
    # Верификация
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT COUNT(*) FROM textbook_toc WHERE textbook_id=:tid"
        ), {"tid": TEXTBOOK_ID}).scalar()
        print(f"[TOC] Verified: {result} entries in DB")

if __name__ == "__main__":
    main()
