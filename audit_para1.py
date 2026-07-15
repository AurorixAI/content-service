import psycopg2
from psycopg2.extras import DictCursor
import json
import os
from collections import Counter

conn = psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://algo_user:algo_password@postgres:5432/algo_db'))
cur = conn.cursor(cursor_factory=DictCursor)

cur.execute('''
    SELECT t.id, tt.exercise_number, t.task_category, t.answer_type, t.skill_id, t.correct_answer as answer_raw, t.distractor_meta as distractors, t.tags 
    FROM tasks_master t 
    JOIN textbook_tasks tt ON t.id = tt.task_id
    WHERE tt.textbook_id = '5a9f7fea-1394-4141-9d58-015972e83acc' 
    AND t.toc_id = 1011
    ORDER BY tt.exercise_number
''')
tasks = cur.fetchall()

total = len(tasks)
types = Counter(t['task_category'] for t in tasks)
answer_types = Counter(t['answer_type'] for t in tasks)
skills = Counter(bool(t['skill_id']) for t in tasks)
verify_modes = Counter(t['tags'].get('answer_verify_mode', 'unknown') if t['tags'] else 'unknown' for t in tasks)
distractor_counts = Counter(len(t['distractors']) if t['distractors'] else 0 for t in tasks)

with open("/app/audit_para1_report.md", "w") as f:
    f.write("# Аудит Параграфа 1 (Действия над действительными числами)\n\n")
    f.write(f"**Всего задач в БД:** {total} (из 48 извлеченных, 4 пропущены как дубли, итого 44 новых записано)\n\n")
    
    f.write("## 1. Категории задач (task_category)\n")
    for k, v in types.items(): f.write(f"- `{k}`: {v} шт\n")
    
    f.write("\n## 2. Типы ответов (answer_type)\n")
    for k, v in answer_types.items(): f.write(f"- `{k}`: {v} шт\n")
    
    f.write("\n## 3. Привязка к навыкам (skill_id)\n")
    f.write(f"- **Есть навык (привязан к графу):** {skills[True]} шт\n")
    f.write(f"- **Без навыка (exam-only):** {skills[False]} шт (уверенность маппинга была < 0.70)\n")
    
    f.write("\n## 4. Верификация Dual Consensus (answer_verify_mode)\n")
    for k, v in verify_modes.items(): f.write(f"- `{k}`: {v} шт\n")
    
    f.write("\n## 5. Дистракторы\n")
    for k, v in distractor_counts.items(): f.write(f"- По **{k}** дистрактора: {v} задач\n")

    f.write("\n## 6. Проблемные задачи (сработала защита)\n")
    unresolved = [t for t in tasks if t['tags'] and t['tags'].get('answer_verify_mode') == 'verify_unresolved']
    if unresolved:
        f.write("\n**Задачи `verify_unresolved` (SymPy не смог доказать равенство Flash и Pro):**\n")
        for t in unresolved:
            f.write(f"- № {t['exercise_number']} (Тип: {t['answer_type']}): `{t['answer_raw']}`\n")
            
    dual_failed = [t for t in tasks if t['tags'] and t['tags'].get('answer_verify_mode') == 'dual_failed']
    if dual_failed:
        f.write("\n**Задачи `dual_failed` (Flash и Pro дали разные ответы):**\n")
        for t in dual_failed:
            f.write(f"- № {t['exercise_number']} (Тип: {t['answer_type']}): `{t['answer_raw']}`\n")
    
    no_distractors = [t for t in tasks if not t['distractors'] and t['tags'].get('answer_verify_mode') == 'match']
    if no_distractors:
        f.write("\n**Успешная верификация, но нет дистракторов:**\n")
        for t in no_distractors:
             f.write(f"- № {t['exercise_number']} (Тип: {t['answer_type']})\n")

print("Audit report written to /app/audit_para1_report.md")
