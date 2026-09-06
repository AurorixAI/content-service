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
print(f"Auditing all {len(rows)} tasks in tasks_master...\n")

issues = {
    "split_commands": [],         # e.g. \le ft, \ge q, \ne q, etc.
    "dfrac_in_exponents": [],     # e.g. ^{\dfrac
    "unbalanced_braces": [],      # { without }
    "unclosed_dollars": [],       # odd number of $
    "glued_cdot": [],             # \cdotx
}

def check_braces(s):
    if not s:
        return True
    depth = 0
    for c in s:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0

def check_dollars(s):
    if not s:
        return True
    cnt = len(re.findall(r"(?<!\\)\$", s))
    return cnt % 2 == 0

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

for r in rows:
    tid, qtext, qlatex, ca, calatex, opts, optslatex, dm = r
    
    opts_str = json.dumps(opts, ensure_ascii=False) if opts else ""
    optsl_str = json.dumps(optslatex, ensure_ascii=False) if optslatex else ""
    dm_str = json.dumps(dm, ensure_ascii=False) if dm else ""
    
    parts = [str(qtext or ""), str(qlatex or ""), str(ca or ""), str(calatex or ""), opts_str, optsl_str, dm_str]
    all_text = " ".join(parts)
    
    # 1. Split commands
    if re.search(r"\\(le\s+ft|ge\s+q|le\s+q|ne\s+q|pm\s+od|ne\s+g)\b", all_text):
        issues["split_commands"].append(tid)
        
    # 2. dfrac in exponents
    if has_dfrac_in_power(all_text):
        issues["dfrac_in_exponents"].append(tid)
        
    # 3. Braces check
    for field_name, f_val in [("qtext", qtext), ("qlatex", qlatex), ("ca", ca), ("calatex", calatex)]:
        if f_val and not check_braces(f_val):
            issues["unbalanced_braces"].append((tid, field_name))
            
    # 4. Dollar check
    for field_name, f_val in [("qtext", qtext), ("qlatex", qlatex), ("ca", ca), ("calatex", calatex)]:
        if f_val and not check_dollars(f_val):
            issues["unclosed_dollars"].append((tid, field_name))
            
    # 5. Glued cdot
    if re.search(r"\\cdot([a-wy-zA-WY-Z]|x\b)", all_text):
        issues["glued_cdot"].append(tid)

print("=== AUDIT RESULTS ACROSS 35,202 TASKS ===")
print(f"1. Ошибочно разбитые команды (\\le ft, \\ge q, и т.д.): {len(issues['split_commands'])}")
print(f"2. \\dfrac внутри показателей степеней/индексов: {len(issues['dfrac_in_exponents'])}")
print(f"3. Несбалансированные фигурные скобки: {len(issues['unbalanced_braces'])}")
print(f"4. Незакрытые знаки $: {len(issues['unclosed_dollars'])}")
print(f"5. Слипшиеся \\cdotx: {len(issues['glued_cdot'])}")

conn.close()
