import psycopg2
import re
import json

conn = psycopg2.connect(dbname="algo_content", user="algo", password="algo_password", host="localhost", port=5434)
cur = conn.cursor()

cur.execute("""
    SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, 
           answer_options, answer_options_latex, distractor_meta
    FROM tasks_master;
""")
rows = cur.fetchall()
print(f"Total tasks in database: {len(rows)}")

def has_dfrac_in_power(text):
    if not text or not isinstance(text, str):
        return False
    i = 0
    while i < len(text):
        if text[i] in ("^", "_"):
            i += 1
            if i < len(text) and text[i] == "{":
                i += 1
                depth = 1
                while i < len(text) and depth > 0:
                    if text.startswith("\\dfrac", i):
                        return True
                    elif text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                    i += 1
            elif text.startswith("\\dfrac", i):
                return True
        else:
            i += 1
    return False

missing_space_re = re.compile(r'\\(cdot|times|pm|mp|approx|ne|neq|le|leq|ge|geq)[a-zA-Z]')

tasks_with_power_dfrac = []
tasks_with_missing_space = []

fields_breakdown = {
    "question_text": 0,
    "question_latex": 0,
    "correct_answer": 0,
    "correct_answer_latex": 0,
    "answer_options": 0,
    "answer_options_latex": 0,
    "distractor_meta": 0,
}

for r in rows:
    tid, qtext, qlatex, ca, calatex, opts, optslatex, dm = r
    
    found_power_issue = False
    
    if has_dfrac_in_power(qtext):
        fields_breakdown["question_text"] += 1
        found_power_issue = True
    if has_dfrac_in_power(qlatex):
        fields_breakdown["question_latex"] += 1
        found_power_issue = True
    if has_dfrac_in_power(ca):
        fields_breakdown["correct_answer"] += 1
        found_power_issue = True
    if has_dfrac_in_power(calatex):
        fields_breakdown["correct_answer_latex"] += 1
        found_power_issue = True
        
    opts_str = json.dumps(opts, ensure_ascii=False) if opts else ""
    if has_dfrac_in_power(opts_str):
        fields_breakdown["answer_options"] += 1
        found_power_issue = True
        
    optsl_str = json.dumps(optslatex, ensure_ascii=False) if optslatex else ""
    if has_dfrac_in_power(optsl_str):
        fields_breakdown["answer_options_latex"] += 1
        found_power_issue = True
        
    dm_str = json.dumps(dm, ensure_ascii=False) if dm else ""
    if has_dfrac_in_power(dm_str):
        fields_breakdown["distractor_meta"] += 1
        found_power_issue = True
        
    if found_power_issue:
        tasks_with_power_dfrac.append(tid)
        
    all_text = f"{qtext or ''} {qlatex or ''} {ca or ''} {calatex or ''} {opts_str} {optsl_str} {dm_str}"
    if missing_space_re.search(all_text):
        tasks_with_missing_space.append(tid)

print(f"\n1. ВСЕГО задач с \\dfrac внутри показателей степеней/индексов: {len(tasks_with_power_dfrac)}")
for k, v in fields_breakdown.items():
    print(f"   - в поле {k}: {v}")

print(f"\n2. Задач со слитными математическими операторами (например, \\cdotx): {len(tasks_with_missing_space)}")

conn.close()
