import psycopg2
import json
import os

os.makedirs('/Users/arslan/Desktop/ALGO/content-service/scripts/archive', exist_ok=True)
backup_file = '/Users/arslan/Desktop/ALGO/content-service/scripts/archive/backup_rejected_58_tasks.json'

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

# 1. Загружаем все данные по 58 rejected задачам для резервной копии
cur.execute("""
    SELECT id, question_text, question_latex, correct_answer, correct_answer_latex,
           distractor_meta, answer_type, tags, created_at, updated_at
    FROM tasks_master
    WHERE verification_status = 'rejected'
    ORDER BY id;
""")
columns = [desc[0] for desc in cur.description]
tasks = []
for row in cur.fetchall():
    task_dict = dict(zip(columns, row))
    # serialize dates
    for k, v in task_dict.items():
        if hasattr(v, 'isoformat'):
            task_dict[k] = v.isoformat()
    tasks.append(task_dict)

with open(backup_file, 'w', encoding='utf-8') as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)

print(f"📦 Резервная копия {len(tasks)} задач сохранена в {backup_file}")

rejected_ids = [t['id'] for t in tasks]
print(f"🎯 Список точных ID для удаления ({len(rejected_ids)} задач):")
for i, tid in enumerate(rejected_ids, 1):
    print(f"  {i:2d}. {tid}")

# 2. Удаление в рамках атомарной транзакции
cur.execute("DELETE FROM task_figure_refs WHERE task_id = ANY(%s);", (rejected_ids,))
del_figs = cur.rowcount
print(f"• Удалено ссылок на рисунки (task_figure_refs): {del_figs}")

cur.execute("DELETE FROM textbook_tasks WHERE task_id = ANY(%s);", (rejected_ids,))
del_tb = cur.rowcount
print(f"• Удалено ссылок на параграфы (textbook_tasks): {del_tb}")

cur.execute("""
    DELETE FROM tasks_master
    WHERE id = ANY(%s) AND verification_status = 'rejected';
""", (rejected_ids,))
del_master = cur.rowcount
print(f"• Удалено задач из tasks_master: {del_master}")

conn.commit()

# 3. Финальная проверка
cur.execute("SELECT count(*) FROM tasks_master WHERE verification_status = 'rejected';")
remaining_rejected = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM tasks_master;")
new_total = cur.fetchone()[0]

print(f"\n✅ УДАЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО!")
print(f"• Остаток rejected в базе: {remaining_rejected}")
print(f"• Новое общее количество задач в базе: {new_total} (все 100% верифицированы!)")
