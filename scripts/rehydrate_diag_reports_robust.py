import psycopg2
import json
import re

def norm(s):
    if not s: return ""
    s = str(s).replace("$", "").replace("\\dfrac", "\\frac").replace("\\quad", "").replace(" ", "").lower().strip()
    return s

conn_c = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
conn_d = psycopg2.connect(dbname='algo_diagnostic', user='algo', password='algo_password', host='127.0.0.1', port=5433)
cur_c = conn_c.cursor()
cur_d = conn_d.cursor()

cur_c.execute("SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, distractor_meta FROM tasks_master")
tasks = []
for r in cur_c.fetchall():
    q_norm = norm(r[2] or r[1])
    tasks.append({
        'id': r[0],
        'qtext': r[1],
        'qlatex': r[2],
        'correct_answer': r[3],
        'calatex': r[4],
        'dmeta': r[5] if r[5] else [],
        'qnorm': q_norm
    })

print(f"Loaded {len(tasks)} master tasks from algo_content DB.")
tasks_by_id = {t['id']: t for t in tasks}

cur_d.execute("SELECT id, session_id, report_json FROM diag_reports")
reports = cur_d.fetchall()

updated = 0
for rid, sid, rjson in reports:
    if isinstance(rjson, str):
        rjson = json.loads(rjson)
        
    changed = False
    for ep in rjson.get('error_patterns', []):
        # Do not guess by a similar question string: duplicated textbook tasks
        # make that non-deterministic.  New report JSON always carries task_id.
        match = tasks_by_id.get(ep.get('task_id'))
        
        if match:
            # Update question_latex & question_text
            clean_q = match['qlatex'] or match['qtext']
            if clean_q and (ep.get('question_latex') != match['qlatex'] or ep.get('question_text') != match['qtext']):
                ep['question_latex'] = match['qlatex']
                ep['question_text'] = match['qtext']
                changed = True
                
            # Update options
            new_opts = []
            new_opts_latex = []
            if match['correct_answer']:
                new_opts.append(match['correct_answer'])
                new_opts_latex.append(match['calatex'] or match['correct_answer'])
            for dm in match['dmeta']:
                if isinstance(dm, dict):
                    val = dm.get('value')
                    if val:
                        new_opts.append(val)
                        new_opts_latex.append(dm.get('value_latex') or val)
            if new_opts and len(new_opts) > 1:
                ep['answer_options'] = new_opts
                ep['answer_options_latex'] = new_opts_latex
                ep['correct_answer'] = match['correct_answer']
                ep['correct_answer_latex'] = match['calatex'] or match['correct_answer']
                changed = True
                
            # Update distractor_explanation if student answer matched a distractor
            st_ans = norm(ep.get('student_answer'))
            for dm in match['dmeta']:
                if isinstance(dm, dict):
                    dval = norm(dm.get('value'))
                    dexp = dm.get('explanation_latex') or dm.get('explanation')
                    if dval and st_ans and (dval in st_ans or st_ans in dval) and dexp:
                        ep['distractor_explanation'] = dexp
                        changed = True
                        break

    if changed:
        cur_d.execute("UPDATE diag_reports SET report_json = %s::jsonb WHERE id = %s", (json.dumps(rjson, ensure_ascii=False), rid))
        updated += 1

conn_d.commit()
print(f"Successfully rehydrated {updated} out of {len(reports)} diagnostic reports with verified master task data!")
