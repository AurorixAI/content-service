import psycopg2, os
from datetime import datetime

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

# 1. Pipeline status
cur.execute('''
    SELECT 
        COALESCE(tags->>'answer_verify_mode', 'pending') as mode,
        COUNT(*) as cnt
    FROM tasks_master
    WHERE toc_id = 1054
    GROUP BY 1
    ORDER BY cnt DESC
''')
stats = cur.fetchall()

# 2. Sample tasks with 'verified_corrected'
cur.execute('''
    SELECT id, question_text, correct_answer, answer_type, distractor_meta
    FROM tasks_master
    WHERE toc_id = 1054 AND tags->>'answer_verify_mode' = 'verified_corrected'
    LIMIT 3
''')
corrected = cur.fetchall()

# 3. Sample tasks with 'verified_match'
cur.execute('''
    SELECT id, question_text, correct_answer, answer_type, distractor_meta
    FROM tasks_master
    WHERE toc_id = 1054 AND tags->>'answer_verify_mode' = 'verified_match'
    LIMIT 3
''')
matches = cur.fetchall()

md = f"# Аудит качества арбитража DeepSeek (Параграф 31)\n\n"
md += f"**Дата и время:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
md += "## 1. Прогресс пайплайна (Параграф 31)\n"
for mode, cnt in stats:
    md += f"- **{mode}**: {cnt}\n"

md += "\n## 2. Примеры: DeepSeek НАШЕЛ И ИСПРАВИЛ ОШИБКУ (`verified_corrected`)\n"
md += "Эти задачи ушли к арбитру, потому что первая модель выдала ответ, отличный от учебника. DeepSeek написал код (SymPy), решил уравнение с нуля, доказал, кто прав (или вычислил новый точный ответ) и сгенерировал под него дистракторы.\n\n"

for task_id, q, a, atype, dists in corrected:
    md += f"### Задача {task_id} (Тип: {atype})\n"
    md += f"**Условие:**\n```text\n{q}\n```\n"
    md += f"**Итоговый правильный ответ (от DeepSeek):** `{a}`\n"
    md += "**Дистракторы:**\n"
    if dists:
        for d in dists:
            md += f"- `{d}`\n"
    md += "\n---\n"

md += "\n## 3. Примеры: DeepSeek ДОКАЗАЛ ЭКВИВАЛЕНТНОСТЬ (`verified_match`)\n"
md += "Разные форматы записи (например, дроби, интервалы) помешали сработать быстрой проверке, но арбитр через SymPy-код доказал, что математически это одно и то же.\n\n"

for task_id, q, a, atype, dists in matches:
    md += f"### Задача {task_id} (Тип: {atype})\n"
    md += f"**Условие:**\n```text\n{q}\n```\n"
    md += f"**Утверждённый ответ:** `{a}`\n"
    md += "**Дистракторы:**\n"
    if dists:
        for d in dists:
            md += f"- `{d}`\n"
    md += "\n---\n"

with open('/tmp/deepseek_audit.md', 'w', encoding='utf-8') as f:
    f.write(md)
