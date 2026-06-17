#!/usr/bin/env python3
"""
Вставляет полный TOC для школьного учебника математики 6 класс (Узбекистан, O'qituvchi, 2017).

Страницы — ориентир из оглавления (PDF 233–238). Для theme_stream пайплайна
границы § определяются заголовками тем в тексте, не page_start.

Использование: python3 /app/scripts/insert_toc_school6.py <textbook_id>
"""
import sys
sys.path.insert(0, "/app")

from src.pipeline.db_writer import DBWriter

TEXTBOOK_ID = sys.argv[1] if len(sys.argv) > 1 else "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8"

TOC = [
    # ── ПОВТОРЕНИЕ (номера 1–4 = заголовки в тексте «1. Натуральные…») ──
    {"level": 1, "number": "Повторение",     "title": "Повторение пройденного в 5 классе",                 "page_start": 3,  "sort_order": 0},
    {"level": 2, "number": "1",              "title": "Натуральные числа",                                  "page_start": 3,  "sort_order": 1,  "parent_number": "Повторение"},
    {"level": 2, "number": "2",              "title": "Обыкновенные дроби",                                 "page_start": 4,  "sort_order": 2,  "parent_number": "Повторение"},
    {"level": 2, "number": "3",              "title": "Десятичные дроби",                                   "page_start": 5,  "sort_order": 3,  "parent_number": "Повторение"},
    {"level": 2, "number": "4",              "title": "Проценты",                                            "page_start": 5,  "sort_order": 4,  "parent_number": "Повторение"},

    # ── ГЛАВА I ────────────────────────────────────────────────────────────
    {"level": 1, "number": "Глава I",        "title": "Признаки делимости чисел",                           "page_start": 6,  "sort_order": 10},
    {"level": 2, "number": "1–2",            "title": "Делители и кратные чисел",                           "page_start": 6,  "sort_order": 11, "parent_number": "Глава I"},
    {"level": 2, "number": "3–5",            "title": "Признаки делимости на 10, 5 и 2",                    "page_start": 10, "sort_order": 12, "parent_number": "Глава I"},
    {"level": 2, "number": "6–7",            "title": "Признаки делимости на 9 и 3",                        "page_start": 13, "sort_order": 13, "parent_number": "Глава I"},
    {"level": 2, "number": "10",             "title": "Простые и составные числа",                          "page_start": 16, "sort_order": 14, "parent_number": "Глава I"},
    {"level": 2, "number": "11–12",          "title": "Разложение числа на простые множители",              "page_start": 19, "sort_order": 15, "parent_number": "Глава I"},
    {"level": 2, "number": "13–14",          "title": "Наибольший общий делитель. Взаимно простые числа",   "page_start": 21, "sort_order": 16, "parent_number": "Глава I"},
    {"level": 2, "number": "15–16",          "title": "Наименьшее общее кратное",                            "page_start": 26, "sort_order": 17, "parent_number": "Глава I"},
    {"level": 2, "number": "Тест I",         "title": "Проверьте себя",                                     "page_start": 30, "sort_order": 18, "parent_number": "Глава I"},

    # ── ГЛАВА II ───────────────────────────────────────────────────────────
    {"level": 1, "number": "Глава II",       "title": "Сложение и вычитание дробей с разными знаменателями","page_start": 31, "sort_order": 20},
    {"level": 2, "number": "19–20",          "title": "Основные свойства дробей",                            "page_start": 31, "sort_order": 21, "parent_number": "Глава II"},
    {"level": 2, "number": "21–23",          "title": "Сокращение дробей",                                   "page_start": 34, "sort_order": 22, "parent_number": "Глава II"},
    {"level": 2, "number": "24–26",          "title": "Приведение дробей к общему знаменателю",              "page_start": 39, "sort_order": 23, "parent_number": "Глава II"},
    {"level": 2, "number": "27–28",          "title": "Сравнение дробей с разными знаменателями",            "page_start": 43, "sort_order": 24, "parent_number": "Глава II"},
    {"level": 2, "number": "31–33",          "title": "Сложение и вычитание дробей с разными знаменателями","page_start": 47, "sort_order": 25, "parent_number": "Глава II"},
    {"level": 2, "number": "34–37",          "title": "Сложение и вычитание смешанных дробей",               "page_start": 51, "sort_order": 26, "parent_number": "Глава II"},
    {"level": 2, "number": "Тест II",        "title": "Проверьте себя",                                     "page_start": 38, "sort_order": 27, "parent_number": "Глава II"},

    # ── ГЛАВА III ──────────────────────────────────────────────────────────
    {"level": 1, "number": "Глава III",      "title": "Умножение и деление обыкновенных дробей",             "page_start": 59, "sort_order": 30},
    {"level": 2, "number": "40–42",          "title": "Умножение обыкновенных дробей и смешанных чисел",     "page_start": 59, "sort_order": 31, "parent_number": "Глава III"},
    {"level": 2, "number": "43–45",          "title": "Нахождение части числа",                              "page_start": 65, "sort_order": 32, "parent_number": "Глава III"},
    {"level": 2, "number": "46–48",          "title": "Распределительный закон умножения и его применение",  "page_start": 68, "sort_order": 33, "parent_number": "Глава III"},
    {"level": 2, "number": "49–50",          "title": "Взаимно обратные числа",                              "page_start": 73, "sort_order": 34, "parent_number": "Глава III"},
    {"level": 2, "number": "51–52",          "title": "Деление обыкновенных дробей",                         "page_start": 78, "sort_order": 35, "parent_number": "Глава III"},
    {"level": 2, "number": "53–54",          "title": "Нахождение числа по его части",                       "page_start": 82, "sort_order": 36, "parent_number": "Глава III"},
    {"level": 2, "number": "Тест III",       "title": "Проверьте себя",                                     "page_start": 87, "sort_order": 37, "parent_number": "Глава III"},

    # ── ГЛАВА IV ───────────────────────────────────────────────────────────
    {"level": 1, "number": "Глава IV",       "title": "Отношение и пропорция",                               "page_start": 88, "sort_order": 40},
    {"level": 2, "number": "57–58",          "title": "Понятие отношения. Пропорции",                        "page_start": 88, "sort_order": 41, "parent_number": "Глава IV"},
    {"level": 2, "number": "59–61",          "title": "Основное свойство пропорции",                         "page_start": 93, "sort_order": 42, "parent_number": "Глава IV"},
    {"level": 2, "number": "62–64",          "title": "Применение основного свойства пропорции",             "page_start": 98, "sort_order": 43, "parent_number": "Глава IV"},
    {"level": 2, "number": "65–66",          "title": "Прямо и обратно пропорциональные величины",           "page_start": 101, "sort_order": 44, "parent_number": "Глава IV"},
    {"level": 2, "number": "69–74",          "title": "Применение прямой и обратной пропорциональности",     "page_start": 106, "sort_order": 45, "parent_number": "Глава IV"},
    {"level": 2, "number": "75–78",          "title": "Масштаб",                                              "page_start": 115, "sort_order": 46, "parent_number": "Глава IV"},
    {"level": 2, "number": "Тест IV",        "title": "Проверьте себя",                                     "page_start": 122, "sort_order": 47, "parent_number": "Глава IV"},

    # ── ГЛАВА V ────────────────────────────────────────────────────────────
    {"level": 1, "number": "Глава V",        "title": "Положительные и отрицательные числа. Целые числа",    "page_start": 123, "sort_order": 50},
    {"level": 2, "number": "81–83",          "title": "Положительные и отрицательные числа. Понятие о целых числах", "page_start": 123, "sort_order": 51, "parent_number": "Глава V"},
    {"level": 2, "number": "84–85",          "title": "Координатная прямая. Изображение положительных и отрицательных чисел", "page_start": 127, "sort_order": 52, "parent_number": "Глава V"},
    {"level": 2, "number": "86–88",          "title": "Противоположные числа. Модуль числа",                 "page_start": 132, "sort_order": 53, "parent_number": "Глава V"},
    {"level": 2, "number": "89–90",          "title": "Сравнение чисел. Изменение величин",                  "page_start": 138, "sort_order": 54, "parent_number": "Глава V"},
    {"level": 2, "number": "Тест V",         "title": "Проверьте себя",                                     "page_start": 144, "sort_order": 55, "parent_number": "Глава V"},

    # ── ГЛАВА VI ───────────────────────────────────────────────────────────
    {"level": 1, "number": "Глава VI",       "title": "Сложение и вычитание положительных и отрицательных чисел", "page_start": 145, "sort_order": 60},
    {"level": 2, "number": "93–94",          "title": "Сложение и вычитание чисел на координатной прямой",   "page_start": 145, "sort_order": 61, "parent_number": "Глава VI"},
    {"level": 2, "number": "95–97",          "title": "Сложение отрицательных чисел",                        "page_start": 149, "sort_order": 62, "parent_number": "Глава VI"},
    {"level": 2, "number": "98–100",         "title": "Сложение чисел с разными знаками",                    "page_start": 152, "sort_order": 63, "parent_number": "Глава VI"},
    {"level": 2, "number": "101–102",        "title": "Вычитание чисел",                                     "page_start": 159, "sort_order": 64, "parent_number": "Глава VI"},
    {"level": 2, "number": "Тест VI",        "title": "Проверьте себя",                                     "page_start": 164, "sort_order": 65, "parent_number": "Глава VI"},

    # ── ГЛАВА VII ──────────────────────────────────────────────────────────
    {"level": 1, "number": "Глава VII",      "title": "Умножение и деление положительных и отрицательных чисел", "page_start": 165, "sort_order": 70},
    {"level": 2, "number": "105–106",        "title": "Умножение чисел",                                     "page_start": 165, "sort_order": 71, "parent_number": "Глава VII"},
    {"level": 2, "number": "107–109",        "title": "Деление чисел",                                       "page_start": 168, "sort_order": 72, "parent_number": "Глава VII"},
    {"level": 2, "number": "110–112",        "title": "Понятие о рациональном числе. Свойства действий над рациональными числами", "page_start": 172, "sort_order": 73, "parent_number": "Глава VII"},
    {"level": 2, "number": "113–114",        "title": "Применение свойств действий с рациональными числами", "page_start": 177, "sort_order": 74, "parent_number": "Глава VII"},
    {"level": 2, "number": "Тест VII",       "title": "Проверьте себя",                                     "page_start": 181, "sort_order": 75, "parent_number": "Глава VII"},

    # ── ГЛАВА VIII ─────────────────────────────────────────────────────────
    {"level": 1, "number": "Глава VIII",     "title": "Решение уравнений",                                   "page_start": 182, "sort_order": 80},
    {"level": 2, "number": "116–117",        "title": "Правило раскрытия скобок. Коэффициент",               "page_start": 182, "sort_order": 81, "parent_number": "Глава VIII"},
    {"level": 2, "number": "118–119",        "title": "Решение линейных уравнений с одним неизвестным",      "page_start": 186, "sort_order": 82, "parent_number": "Глава VIII"},
    {"level": 2, "number": "120–121",        "title": "Простейшие линейные уравнения с одним неизвестным и дробным коэффициентом", "page_start": 192, "sort_order": 83, "parent_number": "Глава VIII"},
    {"level": 2, "number": "Тест VIII",      "title": "Проверьте себя",                                     "page_start": 196, "sort_order": 84, "parent_number": "Глава VIII"},

    # ── ГЛАВА IX ───────────────────────────────────────────────────────────
    {"level": 1, "number": "Глава IX",       "title": "Данные",                                              "page_start": 197, "sort_order": 90},
    {"level": 2, "number": "124–125",        "title": "Таблицы",                                             "page_start": 197, "sort_order": 91, "parent_number": "Глава IX"},
    {"level": 2, "number": "126–127",        "title": "Диаграммы",                                           "page_start": 200, "sort_order": 92, "parent_number": "Глава IX"},
    {"level": 2, "number": "128–129",        "title": "Анализ данных",                                       "page_start": 203, "sort_order": 93, "parent_number": "Глава IX"},
    {"level": 2, "number": "130–131",        "title": "Элементы комбинаторики",                              "page_start": 206, "sort_order": 94, "parent_number": "Глава IX"},
    {"level": 2, "number": "132–133",        "title": "Решение задач при помощи правила умножения",          "page_start": 207, "sort_order": 95, "parent_number": "Глава IX"},
    {"level": 2, "number": "Тест IX",        "title": "Проверьте себя",                                     "page_start": 208, "sort_order": 96, "parent_number": "Глава IX"},

    # ── ГЛАВА X ────────────────────────────────────────────────────────────
    {"level": 1, "number": "Глава X",        "title": "Геометрический материал",                              "page_start": 209, "sort_order": 100},
    {"level": 2, "number": "136–138",        "title": "Треугольник, его периметр, виды треугольников",       "page_start": 209, "sort_order": 101, "parent_number": "Глава X"},
    {"level": 2, "number": "139–142",        "title": "Площадь треугольника",                                "page_start": 213, "sort_order": 102, "parent_number": "Глава X"},
    {"level": 2, "number": "145–146",        "title": "Вычисление площади на клетчатой бумаге",              "page_start": 217, "sort_order": 103, "parent_number": "Глава X"},
    {"level": 2, "number": "147–149",        "title": "Задачи на вычисление площадей на клетчатой бумаге",   "page_start": 220, "sort_order": 104, "parent_number": "Глава X"},
    {"level": 2, "number": "150–152",        "title": "Длина окружности и площадь круга",                    "page_start": 222, "sort_order": 105, "parent_number": "Глава X"},
    {"level": 2, "number": "Тест X",         "title": "Проверьте себя",                                     "page_start": 225, "sort_order": 106, "parent_number": "Глава X"},
]


def main():
    print(f"[school6_toc] Textbook: {TEXTBOOK_ID}")

    writer = DBWriter()
    count = writer.write_toc(TEXTBOOK_ID, TOC)
    print(f"[school6_toc] Done: {count} entries written to DB")


if __name__ == "__main__":
    main()
