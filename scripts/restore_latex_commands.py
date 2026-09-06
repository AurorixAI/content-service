import psycopg2
import json
import re

def restore_latex(s: str) -> str:
    if not s or not isinstance(s, str):
        return s
    s = re.sub(r'\\le\s+ft\b', r'\\left', s)
    s = re.sub(r'\\le\s+q\b', r'\\leq', s)
    s = re.sub(r'\\ge\s+q\b', r'\\geq', s)
    s = re.sub(r'\\ne\s+q\b', r'\\neq', s)
    s = re.sub(r'\\ne\s+g\b', r'\\neg', s)
    s = re.sub(r'\\pm\s+od\b', r'\\pmod', s)
    return s

def restore_json(obj):
    if isinstance(obj, str):
        return restore_latex(obj)
    elif isinstance(obj, list):
        return [restore_json(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: restore_json(v) for k, v in obj.items()}
    return obj

conn = psycopg2.connect(dbname="algo_content", user="algo", password="algo_password", host="localhost", port=5434)
cur = conn.cursor()

cur.execute("""
    SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, 
           answer_options, answer_options_latex, distractor_meta
    FROM tasks_master;
""")
rows = cur.fetchall()
print(f"Scanning {len(rows)} tasks for restore...")

batch_updates = []
for r in rows:
    tid, qtext, qlatex, ca, calatex, opts, optslatex, dm = r
    
    new_qtext = restore_latex(qtext)
    new_qlatex = restore_latex(qlatex)
    new_ca = restore_latex(ca)
    new_calatex = restore_latex(calatex)
    new_opts = restore_json(opts)
    new_optslatex = restore_json(optslatex)
    new_dm = restore_json(dm)
    
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

print(f"Restoring {len(batch_updates)} tasks...")

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
    print(f"Restored {min(i+chunk_size, len(batch_updates))}/{len(batch_updates)} tasks...")

print("Restore completed successfully!")
conn.close()
