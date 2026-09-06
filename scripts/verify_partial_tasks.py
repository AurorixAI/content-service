import psycopg2
import json
import re

KATEX_CHECK_RE = re.compile(r'\$([^$]+)\$')

def is_katex_clean(text: str) -> bool:
    if not text:
        return True
    # Check dollar count parity
    if text.count('$') % 2 != 0:
        return False
    # Check double dollar parity
    if text.count('$$') % 2 != 0:
        return False
    # Check for unescaped broken trig
    if re.search(r'\\(sinx|cosx|tgx|ctgx|arcsinx|arccosx)', text):
        return False
    return True

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

cur.execute("SELECT id, question_latex, correct_answer_latex, distractor_meta FROM tasks_master WHERE latex_status = 'partial';")
rows = cur.fetchall()

clean_count = 0
need_fix_count = 0
clean_ids = []
need_fix_ids = []

for r in rows:
    tid, ql, cal, dm = r[0], r[1], r[2], r[3]
    
    ok = True
    if not is_katex_clean(ql): ok = False
    if not is_katex_clean(cal): ok = False
    for d in (dm or []):
        if isinstance(d, dict):
            if not is_katex_clean(d.get('value_latex')): ok = False
            if not is_katex_clean(d.get('explanation_latex')): ok = False
            if not is_katex_clean(d.get('error_logic_latex')): ok = False
            
    if ok:
        clean_count += 1
        clean_ids.append(tid)
    else:
        need_fix_count += 1
        need_fix_ids.append(tid)

print(f"Total partial tasks: {len(rows)}")
print(f"  - 100% clean LaTeX (just plain text options like '15' or 'невозможно определить'): {clean_count}")
print(f"  - Tasks with unclosed dollars or bad latex: {need_fix_count}")

