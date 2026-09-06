import psycopg2
import json
import re

def clean_latex(s: str) -> str:
    if not s or not isinstance(s, str):
        return s
    # Fix \cdotx -> \cdot x, etc.
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

def clean_json_structure(obj):
    if isinstance(obj, str):
        return clean_latex(obj)
    elif isinstance(obj, list):
        return [clean_json_structure(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: clean_json_structure(v) for k, v in obj.items()}
    return obj

conn = psycopg2.connect(dbname="algo_content", user="algo", password="algo_password", host="localhost", port=5434)
cur = conn.cursor()

cur.execute("""
    SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, 
           answer_options, answer_options_latex, distractor_meta
    FROM tasks_master;
""")
rows = cur.fetchall()
print(f"Checking {len(rows)} tasks...")

updated_count = 0
batch_updates = []

for r in rows:
    tid, qtext, qlatex, ca, calatex, opts, optslatex, dm = r
    
    new_qtext = clean_latex(qtext)
    new_qlatex = clean_latex(qlatex)
    new_ca = clean_latex(ca)
    new_calatex = clean_latex(calatex)
    new_opts = clean_json_structure(opts)
    new_optslatex = clean_json_structure(optslatex)
    new_dm = clean_json_structure(dm)
    
    # Check if changed
    if (new_qtext != qtext or new_qlatex != qlatex or new_ca != ca or 
        new_calatex != calatex or new_opts != opts or new_optslatex != optslatex or new_dm != dm):
        
        batch_updates.append((
            new_qtext,
            new_qlatex,
            new_ca,
            new_calatex,
            json.dumps(new_opts, ensure_ascii=False) if new_opts is not None else None,
            json.dumps(new_optslatex, ensure_ascii=False) if new_optslatex is not None else None,
            json.dumps(new_dm, ensure_ascii=False) if new_dm is not None else None,
            tid
        ))

print(f"Tasks requiring update: {len(batch_updates)}")

# Execute in chunks
chunk_size = 500
for i in range(0, len(batch_updates), chunk_size):
    chunk = batch_updates[i:i+chunk_size]
    for item in chunk:
        cur.execute("""
            UPDATE tasks_master
            SET question_text = %s,
                question_latex = %s,
                correct_answer = %s,
                correct_answer_latex = %s,
                answer_options = %s::jsonb,
                answer_options_latex = %s::jsonb,
                distractor_meta = %s::jsonb
            WHERE id = %s;
        """, item)
    conn.commit()
    print(f"Updated {min(i+chunk_size, len(batch_updates))}/{len(batch_updates)} tasks...")

print("All tasks successfully cleaned up in database!")
conn.close()
