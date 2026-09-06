import psycopg2
import json
import re
import sys

sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service')
from scripts.backfill_latex_deepseek import (
    final_display_issues,
    latex_status_from_issues,
    _json_list
)

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

# 1. Задачи с 0 issues сразу промоутим
cur.execute("""
    SELECT id, question_text, question_latex, correct_answer,
           correct_answer_latex, distractor_meta, answer_options,
           answer_options_latex
    FROM tasks_master
    WHERE latex_status = 'partial' AND verification_status = 'verified';
""")
rows = cur.fetchall()

promoted = 0
for r in rows:
    tid = r[0]
    issues, req = final_display_issues(*r[1:])
    if not issues:
        cur.execute("UPDATE tasks_master SET latex_status = 'verified', latex_normalized_at = NOW() WHERE id = %s;", (tid,))
        promoted += 1

conn.commit()
print(f"🎉 Промоутировано задач с 0 issues: {promoted}!")
