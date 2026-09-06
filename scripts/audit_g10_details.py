import psycopg2
from psycopg2.extras import DictCursor
import os
import re

db_url = os.getenv('DATABASE_URL', 'postgresql://algo:algo_password@content-postgres:5432/algo_content')
conn = psycopg2.connect(db_url)
cur = conn.cursor(cursor_factory=DictCursor)

textbook_id = 'e92457e0-c22d-4485-b838-6962ecd7413f'

cur.execute('''
    SELECT tm.id, tm.question_latex, tm.correct_answer_latex
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    WHERE toc.textbook_id = %s
''', (textbook_id,))
tasks = cur.fetchall()

output = []

output.append("=== SymPy Leaks ===")
for t in tasks:
    ql = t['question_latex'] or ''
    al = t['correct_answer_latex'] or ''
    for field, val in [('question', ql), ('answer', al)]:
        if ' & ' in val or ' ~ ' in val or ' | ' in val:
            output.append(f"Task: {t['id']} | Field: {field} | Val: {val}")

output.append("\n=== Russian in Math Blocks ===")
for t in tasks:
    ql = t['question_latex'] or ''
    al = t['correct_answer_latex'] or ''
    for field, val in [('question', ql), ('answer', al)]:
        math_blocks = re.findall(r'\$(.*?)\$', val)
        for mb in math_blocks:
            cyrillic = re.findall(r'[а-яА-ЯёЁ]', mb)
            if cyrillic:
                clean_mb = mb
                clean_mb = re.sub(r'\\text\{.*?\}', '', clean_mb)
                clean_mb = re.sub(r'\\operatorname\{.*?\}', '', clean_mb)
                if re.findall(r'[а-яА-ЯёЁ]', clean_mb):
                    output.append(f"Task: {t['id']} | Field: {field} | Cyrillic inside block: ${mb}$")
                    break

with open('/app/audit_g10_details.txt', 'w') as f:
    f.write('\n'.join(output))

conn.close()
print("Done writing audit_g10_details.txt")
