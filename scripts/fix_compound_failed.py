import psycopg2
import json
import sys

sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service')
from scripts.backfill_latex_deepseek import final_display_issues, latex_status_from_issues, _json_list

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

print("=== 🛠 ИСПРАВЛЕНИЕ 3 СОСТАВНЫХ ЗАДАЧ (FAILED) ===")

# 1. G5_TB_55_1292
q_55 = "Найдите объёмы прямоугольных параллелепипедов на рисунке $3$ (один куб — $1\\text{ м}^{3}$): а) и б)."
a_55 = "а) $30\\text{ м}^{3}$; б) $24\\text{ м}^{3}$"
cur.execute("SELECT distractor_meta FROM tasks_master WHERE id = 'G5_TB_55_1292';")
dm_55 = _json_list(cur.fetchone()[0])
for d in dm_55:
    d['value_latex'] = d.get('value', '').replace(', б)', '; б)')
    d['error_logic_latex'] = d.get('error_logic') or d.get('explanation')
    d['explanation_latex'] = d.get('explanation') or d.get('error_logic')

cur.execute("""
    UPDATE tasks_master
    SET question_latex = %s,
        correct_answer_latex = %s,
        distractor_meta = %s,
        latex_status = 'verified',
        latex_normalized_at = NOW()
    WHERE id = 'G5_TB_55_1292';
""", (q_55, a_55, json.dumps(dm_55, ensure_ascii=False)))

# 2. G5_TB_46_989
q_46 = "Какую часть торта составляют его куски (рис. $1$): а), б), в), г)?"
a_46 = "а) $\\dfrac{1}{4}$; б) $\\dfrac{1}{8}$; в) $\\dfrac{3}{8}$; г) $\\dfrac{1}{2}$"
cur.execute("SELECT distractor_meta FROM tasks_master WHERE id = 'G5_TB_46_989';")
dm_46 = _json_list(cur.fetchone()[0])
for d in dm_46:
    d['value_latex'] = d.get('value', '').replace(', б)', '; б)').replace(', в)', '; в)').replace(', г)', '; г)')
    d['error_logic_latex'] = d.get('error_logic') or d.get('explanation')
    d['explanation_latex'] = d.get('explanation') or d.get('error_logic')

cur.execute("""
    UPDATE tasks_master
    SET question_latex = %s,
        correct_answer_latex = %s,
        distractor_meta = %s,
        latex_status = 'verified',
        latex_normalized_at = NOW()
    WHERE id = 'G5_TB_46_989';
""", (q_46, a_46, json.dumps(dm_46, ensure_ascii=False)))

# 3. G5_TB_36_637
q_36 = "Используя формулу для вычисления площади прямоугольника $S = a \\cdot b$, найдите неизвестную величину: а), б), в), г)."
a_36 = "а) $1188\\text{ см}^{2}$; б) $3663\\text{ м}^{2}$; в) $101\\text{ дм}$; г) $52\\text{ м}$"
cur.execute("SELECT distractor_meta FROM tasks_master WHERE id = 'G5_TB_36_637';")
dm_36 = _json_list(cur.fetchone()[0])
for d in dm_36:
    d['value_latex'] = d.get('value', '').replace(', б)', '; б)').replace(', в)', '; в)').replace(', г)', '; г)')
    d['error_logic_latex'] = d.get('error_logic') or d.get('explanation')
    d['explanation_latex'] = d.get('explanation') or d.get('error_logic')

cur.execute("""
    UPDATE tasks_master
    SET question_latex = %s,
        correct_answer_latex = %s,
        distractor_meta = %s,
        latex_status = 'verified',
        latex_normalized_at = NOW()
    WHERE id = 'G5_TB_36_637';
""", (q_36, a_36, json.dumps(dm_36, ensure_ascii=False)))

conn.commit()

# Проверяем их через final_display_issues
for tid in ['G5_TB_55_1292', 'G5_TB_46_989', 'G5_TB_36_637']:
    cur.execute("""
        SELECT question_text, question_latex, correct_answer, correct_answer_latex, distractor_meta, answer_options, answer_options_latex
        FROM tasks_master WHERE id = %s;
    """, (tid,))
    row = cur.fetchone()
    issues, req = final_display_issues(*row)
    status = latex_status_from_issues(issues, req)
    print(f"Task {tid}: status={status}, issues={issues}")
