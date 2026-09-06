import psycopg2
import os
import json

db_url = os.getenv('DATABASE_URL', 'postgresql://algo:algo_password@content-postgres:5432/algo_content')
conn = psycopg2.connect(db_url)
cur = conn.cursor()

textbook_id = "0fd78e9c-1688-43fa-aea0-bf3a16030034"

toc = [
  {
    "number": "Повторение",
    "title": "Повторение",
    "level": 1,
    "parent_number": "",
    "page_start": 6,
    "page_end": 23,
    "sort_order": 1
  },
  {
    "number": "1",
    "title": "Квадратичная функция и её график",
    "level": 2,
    "parent_number": "Повторение",
    "page_start": 6,
    "page_end": 8,
    "sort_order": 2
  },
  {
    "number": "2",
    "title": "Квадратное неравенство",
    "level": 2,
    "parent_number": "Повторение",
    "page_start": 9,
    "page_end": 13,
    "sort_order": 3
  },
  {
    "number": "3",
    "title": "Тригонометрические тождества",
    "level": 2,
    "parent_number": "Повторение",
    "page_start": 14,
    "page_end": 19,
    "sort_order": 4
  },
  {
    "number": "4",
    "title": "Арифметическая прогрессия. Геометрическая прогрессия",
    "level": 2,
    "parent_number": "Повторение",
    "page_start": 20,
    "page_end": 23,
    "sort_order": 5
  },
  {
    "number": "Глава 1",
    "title": "Функции",
    "level": 1,
    "parent_number": "",
    "page_start": 24,
    "page_end": 60,
    "sort_order": 6
  },
  {
    "number": "1.1",
    "title": "Функция. Способы задания функции",
    "level": 2,
    "parent_number": "Глава 1",
    "page_start": 24,
    "page_end": 26,
    "sort_order": 7
  },
  {
    "number": "1.2",
    "title": "Область определения и множество значений функции",
    "level": 2,
    "parent_number": "Глава 1",
    "page_start": 27,
    "page_end": 31,
    "sort_order": 8
  },
  {
    "number": "1.3",
    "title": "Арифметические операции над функциями",
    "level": 2,
    "parent_number": "Глава 1",
    "page_start": 32,
    "page_end": 34,
    "sort_order": 9
  },
  {
    "number": "1.4",
    "title": "Сложная, обратная, периодическая функции",
    "level": 2,
    "parent_number": "Глава 1",
    "page_start": 35,
    "page_end": 41,
    "sort_order": 10
  },
  {
    "number": "1.5",
    "title": "Свойства функции",
    "level": 2,
    "parent_number": "Глава 1",
    "page_start": 42,
    "page_end": 46,
    "sort_order": 11
  },
  {
    "number": "1.6",
    "title": "Элементарные преобразования графика функции",
    "level": 2,
    "parent_number": "Глава 1",
    "page_start": 47,
    "page_end": 54,
    "sort_order": 12
  },
  {
    "number": "1.7",
    "title": "Линейное и квадратичное моделирование",
    "level": 2,
    "parent_number": "Глава 1",
    "page_start": 55,
    "page_end": 57,
    "sort_order": 13
  },
  {
    "number": "1.8",
    "title": "Проектная работа",
    "level": 2,
    "parent_number": "Глава 1",
    "page_start": 58,
    "page_end": 60,
    "sort_order": 14
  },
  {
    "number": "Глава 2",
    "title": "Рациональные уравнения и неравенства. Иррациональные уравнения",
    "level": 1,
    "parent_number": "",
    "page_start": 61,
    "page_end": 94,
    "sort_order": 15
  },
  {
    "number": "2.1",
    "title": "Рациональные уравнения",
    "level": 2,
    "parent_number": "Глава 2",
    "page_start": 61,
    "page_end": 69,
    "sort_order": 16
  },
  {
    "number": "2.2",
    "title": "Системы рациональных уравнений",
    "level": 2,
    "parent_number": "Глава 2",
    "page_start": 70,
    "page_end": 73,
    "sort_order": 17
  },
  {
    "number": "2.3",
    "title": "Рациональные неравенства",
    "level": 2,
    "parent_number": "Глава 2",
    "page_start": 74,
    "page_end": 77,
    "sort_order": 18
  },
  {
    "number": "2.4",
    "title": "Системы рациональных неравенств",
    "level": 2,
    "parent_number": "Глава 2",
    "page_start": 78,
    "page_end": 80,
    "sort_order": 19
  },
  {
    "number": "2.5",
    "title": "Иррациональные уравнения",
    "level": 2,
    "parent_number": "Глава 2",
    "page_start": 81,
    "page_end": 86,
    "sort_order": 20
  },
  {
    "number": "2.6",
    "title": "Системы иррациональных уравнений",
    "level": 2,
    "parent_number": "Глава 2",
    "page_start": 87,
    "page_end": 94,
    "sort_order": 21
  },
  {
    "number": "Глава 3",
    "title": "Показательные и логарифмические функции",
    "level": 1,
    "parent_number": "",
    "page_start": 95,
    "page_end": 132,
    "sort_order": 22
  },
  {
    "number": "3.1",
    "title": "Показательная функция",
    "level": 2,
    "parent_number": "Глава 3",
    "page_start": 95,
    "page_end": 98,
    "sort_order": 23
  },
  {
    "number": "3.2",
    "title": "Показательные уравнения",
    "level": 2,
    "parent_number": "Глава 3",
    "page_start": 99,
    "page_end": 101,
    "sort_order": 24
  },
  {
    "number": "3.3",
    "title": "Показательные неравенства",
    "level": 2,
    "parent_number": "Глава 3",
    "page_start": 102,
    "page_end": 103,
    "sort_order": 25
  },
  {
    "number": "3.4",
    "title": "Понятие логарифма. Логарифмическая функция",
    "level": 2,
    "parent_number": "Глава 3",
    "page_start": 104,
    "page_end": 108,
    "sort_order": 26
  },
  {
    "number": "3.5",
    "title": "Тождественное преобразование логарифмических выражений",
    "level": 2,
    "parent_number": "Глава 3",
    "page_start": 109,
    "page_end": 115,
    "sort_order": 27
  },
  {
    "number": "3.6",
    "title": "Логарифмические уравнения",
    "level": 2,
    "parent_number": "Глава 3",
    "page_start": 116,
    "page_end": 118,
    "sort_order": 28
  },
  {
    "number": "3.7",
    "title": "Системы показательных и логарифмических уравнений",
    "level": 2,
    "parent_number": "Глава 3",
    "page_start": 119,
    "page_end": 122,
    "sort_order": 29
  },
  {
    "number": "3.8",
    "title": "Логарифмические неравенства",
    "level": 2,
    "parent_number": "Глава 3",
    "page_start": 123,
    "page_end": 126,
    "sort_order": 30
  },
  {
    "number": "3.9",
    "title": "Применение показательных и логарифмических функций",
    "level": 2,
    "parent_number": "Глава 3",
    "page_start": 127,
    "page_end": 132,
    "sort_order": 31
  },
  {
    "number": "Глава 4",
    "title": "Тригонометрические функции",
    "level": 1,
    "parent_number": "",
    "page_start": 133,
    "page_end": 147,
    "sort_order": 32
  },
  {
    "number": "4.1",
    "title": "Тригонометрические функции. Периодические процессы",
    "level": 2,
    "parent_number": "Глава 4",
    "page_start": 133,
    "page_end": 138,
    "sort_order": 33
  },
  {
    "number": "4.2",
    "title": "Обратные тригонометрические функции и их свойства, графики",
    "level": 2,
    "parent_number": "Глава 4",
    "page_start": 139,
    "page_end": 144,
    "sort_order": 34
  },
  {
    "number": "4.3",
    "title": "Проектная работа",
    "level": 2,
    "parent_number": "Глава 4",
    "page_start": 145,
    "page_end": 147,
    "sort_order": 35
  },
  {
    "number": "Глава 5",
    "title": "Тригонометрические уравнения и неравенства",
    "level": 1,
    "parent_number": "",
    "page_start": 148,
    "page_end": 164,
    "sort_order": 36
  },
  {
    "number": "5.1",
    "title": "Тригонометрические уравнения",
    "level": 2,
    "parent_number": "Глава 5",
    "page_start": 148,
    "page_end": 152,
    "sort_order": 37
  },
  {
    "number": "5.2",
    "title": "Методы решения некоторых тригонометрических уравнений",
    "level": 2,
    "parent_number": "Глава 5",
    "page_start": 153,
    "page_end": 156,
    "sort_order": 38
  },
  {
    "number": "5.3",
    "title": "Тригонометрические неравенства",
    "level": 2,
    "parent_number": "Глава 5",
    "page_start": 157,
    "page_end": 164,
    "sort_order": 39
  },
  {
    "number": "Глава 6",
    "title": "Теория вероятностей",
    "level": 1,
    "parent_number": "",
    "page_start": 165,
    "page_end": 192,
    "sort_order": 40
  },
  {
    "number": "6.1",
    "title": "Случайные события",
    "level": 2,
    "parent_number": "Глава 6",
    "page_start": 165,
    "page_end": 167,
    "sort_order": 41
  },
  {
    "number": "6.2",
    "title": "Определения вероятности",
    "level": 2,
    "parent_number": "Глава 6",
    "page_start": 168,
    "page_end": 192,
    "sort_order": 42
  }
]

try:
    # 1. Clear existing TOC entries
    cur.execute("DELETE FROM textbook_toc WHERE textbook_id = %s", (textbook_id,))
    print(f"Cleared existing TOC entries for textbook {textbook_id}")

    # 2. Write new TOC entries with hierarchy and correct page values
    inserted_chapters = {}  # number -> DB id
    
    for idx, entry in enumerate(toc):
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
            
    conn.commit()
    print(f"Successfully inserted {len(toc)} clean TOC entries for the local Uzbek 10th grade textbook!")
except Exception as e:
    conn.rollback()
    print(f"Error: {e}")
finally:
    conn.close()
