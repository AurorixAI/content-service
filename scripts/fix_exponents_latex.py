import psycopg2
import json
import re

def clean_latex(s: str) -> str:
    if not s:
        return s
    # Fix \cdotx -> \cdot x
    s = re.sub(r'\\(cdot|times|pm|mp|approx|ne|neq|le|leq|ge|geq)([a-zA-Z])', r'\\\1 \2', s)
    out = []
    i = 0
    while i < len(s):
        if s[i] in ("^", "_"):
            out.append(s[i])
            i += 1
            if i < len(s) and s[i] == "{":
                out.append("{")
                i += 1
                depth = 1
                while i < len(s) and depth > 0:
                    if s.startswith("\\dfrac", i):
                        out.append("\\frac")
                        i += 6
                    elif s[i] == "{":
                        depth += 1
                        out.append("{")
                        i += 1
                    elif s[i] == "}":
                        depth -= 1
                        out.append("}")
                        i += 1
                    else:
                        out.append(s[i])
                        i += 1
            elif s.startswith("\\dfrac", i):
                out.append("\\frac")
                i += 6
            continue
        else:
            out.append(s[i])
            i += 1
    return "".join(out)

conn = psycopg2.connect(dbname="algo_content", user="algo", password="algo_password", host="localhost", port=5434)
cur = conn.cursor()

cur.execute("""
    SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, answer_options, answer_options_latex
    FROM tasks_master
    WHERE question_text LIKE '%^{\\dfrac%' 
       OR question_latex LIKE '%^{\\dfrac%'
       OR answer_options_latex::text LIKE '%^{\\\\dfrac%'
       OR id = 'ds_llm_8e5dfb4d6c80';
""")

rows = cur.fetchall()
print(f"Found {len(rows)} tasks to clean up in database")

updated = 0
for r in rows:
    tid, qtext, qlatex, ca, calatex, opts, optslatex = r
    new_qtext = clean_latex(qtext)
    new_qlatex = clean_latex(qlatex)
    new_ca = clean_latex(ca)
    new_calatex = clean_latex(calatex)
    
    new_opts = []
    if isinstance(opts, list):
        for o in opts:
            if isinstance(o, dict):
                o_copy = dict(o)
                if "text" in o_copy:
                    o_copy["text"] = clean_latex(o_copy["text"])
                new_opts.append(o_copy)
            else:
                new_opts.append(clean_latex(str(o)))
    else:
        new_opts = opts
        
    new_optslatex = []
    if isinstance(optslatex, list):
        for o in optslatex:
            new_optslatex.append(clean_latex(str(o)))
    else:
        new_optslatex = optslatex
        
    cur.execute("""
        UPDATE tasks_master
        SET question_text = %s,
            question_latex = %s,
            correct_answer = %s,
            correct_answer_latex = %s,
            answer_options = %s::jsonb,
            answer_options_latex = %s::jsonb
        WHERE id = %s;
    """, (new_qtext, new_qlatex, new_ca, new_calatex, json.dumps(new_opts, ensure_ascii=False), json.dumps(new_optslatex, ensure_ascii=False), tid))
    updated += 1

conn.commit()
print(f"Cleaned up {updated} tasks in tasks_master!")
conn.close()
