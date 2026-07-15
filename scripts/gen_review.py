import psycopg2, os
import psycopg2.extras

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

cur.execute('''
    SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
           tm.tags->>'quarantine_v3_ai_answer' as ai1,
           tm.tags->>'quarantine_v3_ai2_answer' as ai2
    FROM tasks_master tm
    WHERE tm.toc_id >= 1015 AND tm.tags->>'quarantine_v3_needs_review' = 'true'
    ORDER BY tm.answer_type, tm.id
''')
tasks = [dict(r) for r in cur.fetchall()]

md_path = '/app/data/g9_detailed_review.md'
with open(md_path, 'w', encoding='utf-8') as f:
    f.write('# Глубокий анализ оставшихся 67 задач (Human Review)\n\n')
    f.write('В этом документе собраны все неразрешенные конфликты для ручного экспертного разбора.\n\n')
    
    current_type = None
    for i, t in enumerate(tasks, 1):
        if t['answer_type'] != current_type:
            current_type = t['answer_type']
            f.write(f'## Тип ответа: {current_type.upper()}\n\n')
            
        f.write(f'### {i}. [{t["id"]}]\n')
        f.write(f'**Условие:** {t["question_text"]}\n\n')
        f.write(f'- **Учебник:** `{t["correct_answer"]}`\n')
        f.write(f'- **ИИ 1:** `{t["ai1"]}`\n')
        if t['ai2']:
            f.write(f'- **ИИ 2:** `{t["ai2"]}`\n')
        f.write('\n---\n\n')

print(f'Wrote {len(tasks)} tasks to {md_path}')
