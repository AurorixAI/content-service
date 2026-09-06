import psycopg2, os, json
from datetime import datetime

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

def fetch(query):
    cur.execute(query)
    return cur.fetchall()

total_tasks = fetch("SELECT COUNT(*) FROM tasks_master tm JOIN textbook_toc toc ON toc.id = tm.toc_id JOIN textbooks tb ON tb.textbook_id = toc.textbook_id WHERE tb.class_level = 9")[0][0]

distractor_query = '''
    SELECT 
        SUM(CASE WHEN jsonb_array_length(COALESCE(distractor_meta, '[]'::jsonb)) >= 3 THEN 1 ELSE 0 END) as d3,
        SUM(CASE WHEN jsonb_array_length(COALESCE(distractor_meta, '[]'::jsonb)) = 0 THEN 1 ELSE 0 END) as d0
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
    WHERE tb.class_level = 9
'''
d3, d0 = fetch(distractor_query)[0]

verify_modes = fetch('''
    SELECT COALESCE(tags->>'answer_verify_mode', 'pending'), COUNT(*)
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
    WHERE tb.class_level = 9
    GROUP BY 1 ORDER BY 2 DESC
''')
mode_map = dict(verify_modes)
verified = mode_map.get('match', 0) + mode_map.get('verified_match', 0) + mode_map.get('verified_corrected', 0) + mode_map.get('sympy_match', 0)
hr = mode_map.get('needs_human_review', 0)
dual_failed = mode_map.get('dual_failed', 0)
unresolved = mode_map.get('unresolved', 0)
skipped = mode_map.get('skipped', 0) + mode_map.get('skipped_type', 0)

garbage_count = fetch('''
    SELECT COUNT(*)
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
    WHERE tb.class_level = 9 AND skill_id IS NULL
''')[0][0]

md = f"""# Детальный аудит качества базы: 9 класс

**Дата и время:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 1. Общее состояние базы (Математическая сверка)

| Метрика | Значение | % от базы |
|---|---|---|
| **Всего задач в 9 классе** | **{total_tasks}** | 100% |
| 🛡 **Верифицировано математически** | {verified} | {verified*100//total_tasks}% |
| 🎯 **Полноценные дистракторы (≥3 шт.)** | {d3} | {d3*100//total_tasks}% |
| ❌ Отсутствуют дистракторы | {d0} | {d0*100//total_tasks}% |
| 👁 Human Review (требуют внимания) | {hr} | {hr*100//total_tasks}% |
| ⚠️ Сложные конфликты (unresolved/dual_failed) | {dual_failed + unresolved} | {(dual_failed + unresolved)*100//total_tasks}% |
| 🗑 OCR-мусор (отсутствуют навыки/skill_id) | {garbage_count} | {garbage_count*100//total_tasks}% |
| ⏭ Пропущено (текст, графики) | {skipped} | {skipped*100//total_tasks}% |

## 2. Разбор математических конфликтов и арбитража

- **Идеальное совпадение (`match`):** {mode_map.get('match', 0)}
- **Доказано арбитром (`verified_corrected`):** {mode_map.get('verified_corrected', 0)} (DeepSeek математически исправил ответы)
- **Доказано эквивалентность (`verified_match`):** {mode_map.get('verified_match', 0)}
- **Подтверждено SymPy (`sympy_match`):** {mode_map.get('sympy_match', 0)}

## 3. Распределение по типам математических ответов

| Тип ответа | Всего | Дистракторы ≥3 | Проблемные | Покрытие |
|---|---|---|---|---|
"""

types_stats = fetch('''
    SELECT 
        tm.answer_type,
        COUNT(*),
        SUM(CASE WHEN jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) >= 3 THEN 1 ELSE 0 END),
        SUM(CASE WHEN tags->>'answer_verify_mode' IN ('unresolved', 'dual_failed', 'failed_at_llm') THEN 1 ELSE 0 END)
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
    WHERE tb.class_level = 9
    GROUP BY 1 ORDER BY 2 DESC
''')

for t, total, dist3, prob in types_stats:
    cov = dist3 * 100 // total if total else 0
    icon = '✅' if cov >= 90 else '⚠️' if cov >= 70 else '🔴'
    md += f"| {t} | {total} | {dist3} | {prob} | {cov}% {icon} |\n"

md += "\n## 4. Состояние по параграфам (Топ-10 проблемных)\n\n"
md += "| Параграф | Всего | Дистракторы ≥3 | Human Review | Мусор | Статус |\n"
md += "|---|---|---|---|---|---|\n"

para_stats = fetch('''
    SELECT 
        toc.title,
        COUNT(*),
        SUM(CASE WHEN jsonb_array_length(COALESCE(tm.distractor_meta, '[]'::jsonb)) >= 3 THEN 1 ELSE 0 END),
        SUM(CASE WHEN tm.tags->>'smart_verify_status' = 'needs_human_review' THEN 1 ELSE 0 END),
        SUM(CASE WHEN tm.skill_id IS NULL THEN 1 ELSE 0 END)
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
    WHERE tb.class_level = 9
    GROUP BY 1 ORDER BY 5 DESC, 4 DESC, 2 DESC
    LIMIT 10
''')

for name, total, dist3, hr_val, garbage in para_stats:
    cov = dist3 * 100 // total if total else 0
    status = '🔴 Ошибка' if garbage > 0 or hr_val > 0 else '🟡 В процессе' if cov < 90 else '✅ Готово'
    short_name = name[:40] + ('...' if len(name) > 40 else '')
    md += f"| {short_name} | {total} | {dist3} | {hr_val} | {garbage} | {status} |\n"

print(md)
