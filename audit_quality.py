import psycopg2
from psycopg2.extras import DictCursor
import json
import os
import random

conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://algo_user:algo_password@postgres:5432/algo_db'))
cur = conn.cursor(cursor_factory=DictCursor)

cur.execute('''
    SELECT tt.exercise_number, t.answer_type, t.correct_answer, t.distractor_meta 
    FROM tasks_master t 
    JOIN textbook_tasks tt ON t.id = tt.task_id
    WHERE t.toc_id IN (1015, 1016)
    AND t.distractor_meta IS NOT NULL 
    AND jsonb_array_length(t.distractor_meta) > 0
    ORDER BY tt.exercise_number
''')
tasks = cur.fetchall()

print(f"Total tasks retrieved for quality check: {len(tasks)}")
sample = random.sample(tasks, min(3, len(tasks)))

for t in sample:
    print("="*60)
    print(f"Задача № {t['exercise_number']}")
    print(f"Тип ответа: {t['answer_type']}")
    print(f"Правильный ответ: {t['correct_answer']}")
    print("\nДистракторы и их логика (ошибки):")
    for d in t['distractor_meta']:
        print(f"  - Вариант: {d.get('answer_raw')}")
        print(f"    Логика: {d.get('error_reasoning')}")
print("="*60)
