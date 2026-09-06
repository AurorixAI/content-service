import psycopg2
import json
import re

def fix_nested_dollars(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    
    # Fix nested dollars like \dfrac{1}{$x^{2}$} -> \dfrac{1}{x^{2}}
    # Or $...$...$...$
    # Pattern: inside a math string, nested $...$ should be stripped
    def unnest(m):
        inner = m.group(0)
        # If inner contains nested $, remove inner $
        # E.g. $f'(x) = \dfrac{1}{$x^{2}$} > 0$
        # matches outer $...$
        content = inner[1:-1]
        if '$' in content:
            content = content.replace('$', '')
        return f"${content}$"

    # Match outer $...$
    # We can clean \dfrac{a}{$b$} or \sqrt{$a$} directly with regex first
    text = re.sub(r'\\dfrac\{([^}]+)\}\{\$([^$]+)\$\}', r'\\dfrac{\1}{\2}', text)
    text = re.sub(r'\\dfrac\{\$([^$]+)\$\}\{([^}]+)\}', r'\\dfrac{\1}{\2}', text)
    text = re.sub(r'\\dfrac\{\$([^$]+)\$\}\{\$([^$]+)\$\}', r'\\dfrac{\1}{\2}', text)
    text = re.sub(r'\\sqrt\{\$([^$]+)\$\}', r'\\sqrt{\1}', text)
    
    # General fix for any $ nested inside $
    # Find all $...$ pairs
    parts = text.split('$')
    if len(parts) > 3:
        # e.g. ["", "f'(x) = \\dfrac{1}{", "x^{2}", "} > 0", ""]
        # If middle parts look like a single math expression, re-join them cleanly
        cleaned_parts = []
        in_math = False
        math_buf = []
        for i, p in enumerate(parts):
            if i % 2 == 1: # math
                math_buf.append(p)
            else: # text
                if math_buf:
                    cleaned_parts.append('$' + ''.join(math_buf) + '$')
                    math_buf = []
                cleaned_parts.append(p)
        if math_buf:
            cleaned_parts.append('$' + ''.join(math_buf) + '$')
        text = ''.join(cleaned_parts)

    return text

def clean_dict_recursive(d):
    if isinstance(d, dict):
        return {k: clean_dict_recursive(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [clean_dict_recursive(x) for x in d]
    elif isinstance(d, str):
        return fix_nested_dollars(d)
    return d

conn_c = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
conn_d = psycopg2.connect(dbname='algo_diagnostic', user='algo', password='algo_password', host='127.0.0.1', port=5433)
cur_c = conn_c.cursor()
cur_d = conn_d.cursor()

cur_c.execute("SELECT id, question_latex, correct_answer_latex, distractor_meta FROM tasks_master")
tasks = cur_c.fetchall()

updated = 0
for r in tasks:
    tid, ql, cal, dm = r[0], r[1], r[2], r[3]
    new_ql = fix_nested_dollars(ql) if ql else None
    new_cal = fix_nested_dollars(cal) if cal else None
    new_dm = clean_dict_recursive(dm) if dm else None
    
    if new_ql != ql or new_cal != cal or new_dm != dm:
        cur_c.execute("""
            UPDATE tasks_master
            SET question_latex = %s,
                correct_answer_latex = %s,
                distractor_meta = %s::jsonb
            WHERE id = %s
        """, (new_ql, new_cal, json.dumps(new_dm, ensure_ascii=False) if new_dm else None, tid))
        updated += 1

conn_c.commit()
print(f"Sanitized nested dollars in {updated} tasks in tasks_master.")

# Clean diag_reports as well
cur_d.execute("SELECT id, report_json FROM diag_reports")
reports = cur_d.fetchall()

updated_rep = 0
for r in reports:
    rid, rjson = r[0], r[1]
    if isinstance(rjson, str): rjson = json.loads(rjson)
    cleaned = clean_dict_recursive(rjson)
    if cleaned != rjson:
        cur_d.execute("UPDATE diag_reports SET report_json = %s::jsonb WHERE id = %s", (json.dumps(cleaned, ensure_ascii=False), rid))
        updated_rep += 1

conn_d.commit()
print(f"Sanitized nested dollars in {updated_rep} reports in diag_reports.")
