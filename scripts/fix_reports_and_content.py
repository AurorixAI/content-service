import psycopg2
import json
import re

def clean_latex_string(s: str) -> str:
    if not isinstance(s, str) or not s:
        return s
    
    # 1. Fix merged LaTeX commands
    s = re.sub(r'\\Deltax\b', r'\\Delta x', s)
    s = re.sub(r'\\quad([a-zA-Z])', r'\\quad \1', s)
    s = re.sub(r'\\qquad([a-zA-Z])', r'\\qquad \1', s)
    s = re.sub(r'\\inftym\b', r'\\infty', s)
    
    # 2. Fix unclosed $(-\infty
    s = s.replace('$(-\\infty', '$(-\\infty')
    s = s.replace('$(- \\infty', '$(-\\infty')
    
    # 3. Fix unescaped x^{-1} or x^{2} outside dollars
    # If string contains x^{-1} without $, wrap in $
    s = re.sub(r'(?<!\$)\bx\^\{(-?\d+)\}(?!\$)', r'$x^{\1}$', s)
    
    # 4. Fix double backslashes in \Deltax or \quady
    s = s.replace('\\Deltax', '\\Delta x')
    s = s.replace('\\quady', '\\quad y')
    
    return s

def clean_dict_recursive(d):
    if isinstance(d, dict):
        return {k: clean_dict_recursive(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [clean_dict_recursive(x) for x in d]
    elif isinstance(d, str):
        return clean_latex_string(d)
    return d

conn_c = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
conn_d = psycopg2.connect(dbname='algo_diagnostic', user='algo', password='algo_password', host='127.0.0.1', port=5433)
cur_c = conn_c.cursor()
cur_d = conn_d.cursor()

print("=== 1. Cleaning algo_content.tasks_master ===")
cur_c.execute("SELECT id, question_text, question_latex, correct_answer_latex, distractor_meta FROM tasks_master")
tasks = cur_c.fetchall()

updated_tasks = 0
for r in tasks:
    tid, qt, ql, cal, dm = r[0], r[1], r[2], r[3], r[4]
    
    new_ql = clean_latex_string(ql) if ql else None
    new_cal = clean_latex_string(cal) if cal else None
    new_dm = clean_dict_recursive(dm) if dm else None
    
    if new_ql != ql or new_cal != cal or new_dm != dm:
        cur_c.execute("""
            UPDATE tasks_master
            SET question_latex = %s,
                correct_answer_latex = %s,
                distractor_meta = %s::jsonb
            WHERE id = %s
        """, (new_ql, new_cal, json.dumps(new_dm, ensure_ascii=False) if new_dm else None, tid))
        updated_tasks += 1

conn_c.commit()
print(f"Updated {updated_tasks} tasks in tasks_master.")

print("\n=== 2. Cleaning algo_diagnostic.diag_reports ===")
cur_d.execute("SELECT id, report_json FROM diag_reports")
reports = cur_d.fetchall()

updated_reports = 0
for r in reports:
    rid, rjson = r[0], r[1]
    if isinstance(rjson, str):
        rjson = json.loads(rjson)
        
    cleaned_json = clean_dict_recursive(rjson)
    
    if cleaned_json != rjson:
        cur_d.execute("UPDATE diag_reports SET report_json = %s::jsonb WHERE id = %s",
                      (json.dumps(cleaned_json, ensure_ascii=False), rid))
        updated_reports += 1

conn_d.commit()
print(f"Updated {updated_reports} reports in diag_reports.")
