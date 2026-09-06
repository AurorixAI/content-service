import sys
import psycopg2

db_url = "postgresql://algo:algo_password@localhost:5432/algo_content"
textbook_id = "e92457e0-c22d-4485-b838-6962ecd7413f"

# We map each entry to its exact PDF page range (1-indexed PDF page numbers)
TOC = [
    # ГЛАВА 1 (PDF offset = 0)
    {"level": 1, "number": "Глава 1", "title": "Повторение и расширение сведений о функции", "page_start": 5, "page_end": 49},
    {"level": 2, "number": "§ 1", "title": "Наибольшее и наименьшее значения функции. Чётные и нечётные функции", "page_start": 5, "page_end": 15, "parent_number": "Глава 1"},
    {"level": 2, "number": "§ 2", "title": "Построение графиков функций с помощью геометрических преобразований", "page_start": 16, "page_end": 20, "parent_number": "Глава 1"},
    {"level": 2, "number": "§ 3", "title": "Обратная функция", "page_start": 21, "page_end": 27, "parent_number": "Глава 1"},
    {"level": 2, "number": "§ 4", "title": "Равносильные уравнения и неравенства", "page_start": 28, "page_end": 35, "parent_number": "Глава 1"},
    {"level": 2, "number": "§ 5", "title": "Метод интервалов", "page_start": 36, "page_end": 43, "parent_number": "Глава 1"},
    {"level": 2, "number": "•", "title": "Применение свойств функций", "page_start": 44, "page_end": 47, "parent_number": "Глава 1"},

    # ГЛАВА 2 (PDF offset = 0)
    {"level": 1, "number": "Глава 2", "title": "Степенная функция", "page_start": 50, "page_end": 109},
    {"level": 2, "number": "§ 6", "title": "Степенная функция с натуральным показателем", "page_start": 50, "page_end": 54, "parent_number": "Глава 2"},
    {"level": 2, "number": "§ 7", "title": "Степенная функция с целым показателем", "page_start": 55, "page_end": 60, "parent_number": "Глава 2"},
    {"level": 2, "number": "§ 8", "title": "Определение корня n-й степени. Функция y = √[n]x", "page_start": 61, "page_end": 69, "parent_number": "Глава 2"},
    {"level": 2, "number": "§ 9", "title": "Свойства корня n-й степени", "page_start": 70, "page_end": 79, "parent_number": "Глава 2"},
    {"level": 2, "number": "§ 10", "title": "Определение и свойства степени с рациональным показателем", "page_start": 80, "page_end": 89, "parent_number": "Глава 2"},
    {"level": 2, "number": "§ 11", "title": "Иррациональные уравнения", "page_start": 90, "page_end": 95, "parent_number": "Глава 2"},
    {"level": 2, "number": "§ 12", "title": "Метод равносильных преобразований для решения иррациональных уравнений", "page_start": 96, "page_end": 99, "parent_number": "Глава 2"},
    {"level": 2, "number": "§ 13", "title": "Иррациональные неравенства", "page_start": 100, "page_end": 102, "parent_number": "Глава 2"},
    {"level": 2, "number": "•", "title": "Примеры решения более сложных иррациональных уравнений и неравенств, а также их систем", "page_start": 103, "page_end": 107, "parent_number": "Глава 2"},

    # ГЛАВА 3 (PDF offset = 0)
    {"level": 1, "number": "Глава 3", "title": "Тригонометрические функции", "page_start": 110, "page_end": 189},
    {"level": 2, "number": "§ 14", "title": "Радианная мера угла", "page_start": 110, "page_end": 115, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 15", "title": "Тригонометрические функции числового аргумента", "page_start": 116, "page_end": 123, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 16", "title": "Знаки значений тригонометрических функций. Чётность и нечётность тригонометрических функций", "page_start": 124, "page_end": 128, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 17", "title": "Периодические функции", "page_start": 129, "page_end": 133, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 18", "title": "Свойства и графики функций y = sin x и y = cos x", "page_start": 134, "page_end": 142, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 19", "title": "Свойства и графики функций y = tan x и y = cot x", "page_start": 143, "page_end": 148, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 20", "title": "Основные соотношения между тригонометрическими функциями одного и того же аргумента", "page_start": 149, "page_end": 154, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 21", "title": "Формулы сложения", "page_start": 155, "page_end": 161, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 22", "title": "Формулы приведения", "page_start": 162, "page_end": 166, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 23", "title": "Формулы двойного и половинного углов", "page_start": 167, "page_end": 177, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 24", "title": "Сумма и разность синусов (косинусов)", "page_start": 178, "page_end": 181, "parent_number": "Глава 3"},
    {"level": 2, "number": "§ 25", "title": "Формулы преобразования произведения тригонометрических функций в сумму", "page_start": 182, "page_end": 184, "parent_number": "Глава 3"},
    {"level": 2, "number": "•", "title": "Гармонические колебания", "page_start": 185, "page_end": 187, "parent_number": "Глава 3"},

    # ГЛАВА 4 (PDF offset = -2)
    {"level": 1, "number": "Глава 4", "title": "Тригонометрические уравнения и неравенства", "page_start": 189, "page_end": 233},
    {"level": 2, "number": "§ 26", "title": "Уравнение cos x = b", "page_start": 189, "page_end": 193, "parent_number": "Глава 4"},
    {"level": 2, "number": "§ 27", "title": "Уравнение sin x = b", "page_start": 194, "page_end": 198, "parent_number": "Глава 4"},
    {"level": 2, "number": "§ 28", "title": "Уравнения tg x = b и ctg x = b", "page_start": 199, "page_end": 203, "parent_number": "Глава 4"},
    {"level": 2, "number": "§ 29", "title": "Функции y = arccos x, y = arcsin x, y = arctg x и y = arcctg x", "page_start": 204, "page_end": 214, "parent_number": "Глава 4"},
    {"level": 2, "number": "§ 30", "title": "Тригонометрические уравнения, сводящиеся к алгебраическим", "page_start": 215, "page_end": 220, "parent_number": "Глава 4"},
    {"level": 2, "number": "§ 31", "title": "Решение тригонометрических уравнений методом разложения на множители", "page_start": 221, "page_end": 223, "parent_number": "Глава 4"},
    {"level": 2, "number": "•", "title": "Примеры решения более сложных тригонометрических уравнений", "page_start": 224, "page_end": 225, "parent_number": "Глава 4"},
    {"level": 2, "number": "§ 32", "title": "Решение простейших тригонометрических неравенств", "page_start": 226, "page_end": 232, "parent_number": "Глава 4"},
    {"level": 2, "number": "•", "title": "Примеры решения более сложных тригонометрических неравенств", "page_start": 233, "page_end": 235, "parent_number": "Глава 4"},

    # ГЛАВА 5 (PDF offset = -5, then -6 at page 303)
    {"level": 1, "number": "Глава 5", "title": "Производная и её применение", "page_start": 234, "page_end": 309},
    {"level": 2, "number": "§ 33", "title": "Представление о пределе функции в точке и о непрерывности функции в точке", "page_start": 234, "page_end": 239, "parent_number": "Глава 5"},
    {"level": 2, "number": "§ 34", "title": "Задачи о мгновенной скорости и касательной к графику функции", "page_start": 240, "page_end": 245, "parent_number": "Глава 5"},
    {"level": 2, "number": "§ 35", "title": "Понятие производной", "page_start": 246, "page_end": 255, "parent_number": "Глава 5"},
    {"level": 2, "number": "§ 36", "title": "Правила вычисления производных", "page_start": 256, "page_end": 264, "parent_number": "Глава 5"},
    {"level": 2, "number": "§ 37", "title": "Уравнение касательной", "page_start": 265, "page_end": 269, "parent_number": "Глава 5"},
    {"level": 2, "number": "§ 38", "title": "Признаки возрастания и убывания функции", "page_start": 270, "page_end": 275, "parent_number": "Глава 5"},
    {"level": 2, "number": "§ 39", "title": "Точки экстремума функции", "page_start": 276, "page_end": 286, "parent_number": "Глава 5"},
    {"level": 2, "number": "§ 40", "title": "Применение производной при нахождении наибольшего и наименьшего значений функции", "page_start": 287, "page_end": 293, "parent_number": "Глава 5"},
    {"level": 2, "number": "§ 41", "title": "Построение графиков функций", "page_start": 294, "page_end": 296, "parent_number": "Глава 5"},
    {"level": 2, "number": "•", "title": "Вторая производная", "page_start": 297, "page_end": 300, "parent_number": "Глава 5"},
    {"level": 2, "number": "•", "title": "Применение производной для решения уравнений и доказательства неравенств", "page_start": 301, "page_end": 303, "parent_number": "Глава 5"},
    {"level": 2, "number": "•", "title": "«Алеф-17»", "page_start": 304, "page_end": 306, "parent_number": "Глава 5"},

    # ВНЕГЛАВОВЫЕ РАЗДЕЛЫ
    {"level": 2, "number": "§ 42", "title": "Упражнения для повторения курса алгебры и начал математического анализа 10 класса", "page_start": 310, "page_end": 319}
]

from src.core.config import get_settings
settings = get_settings()
db_url = settings.database_url

conn = psycopg2.connect(db_url)
try:
    with conn:
        with conn.cursor() as cur:
            # Сначала очистим существующий TOC для этого учебника
            cur.execute("DELETE FROM textbook_toc WHERE textbook_id = %s", (textbook_id,))
            print(f"Cleared existing TOC entries for textbook {textbook_id}")

            # Теперь вставим новый TOC с правильной иерархией parent_id
            inserted_chapters = {}  # number -> DB id
            
            for idx, entry in enumerate(TOC):
                parent_number = entry.get("parent_number")
                parent_id = None
                if parent_number:
                    parent_id = inserted_chapters.get(parent_number)
                
                cur.execute(
                    """
                    INSERT INTO textbook_toc (textbook_id, parent_id, level, number, title, page_start, page_end, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        textbook_id,
                        parent_id,
                        entry["level"],
                        entry["number"],
                        entry["title"],
                        entry["page_start"],
                        entry["page_end"],
                        idx + 1
                    )
                )
                db_id = cur.fetchone()[0]
                if entry["level"] == 1:
                    inserted_chapters[entry["number"]] = db_id
            
            print(f"Successfully inserted {len(TOC)} custom TOC entries with shifted PDF pages.")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
