import psycopg2
import json
import re

conn_c = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
conn_d = psycopg2.connect(dbname='algo_diagnostic', user='algo', password='algo_password', host='127.0.0.1', port=5433)

cur_c = conn_c.cursor()
cur_d = conn_d.cursor()

# 1. Load all master tasks
cur_c.execute("SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, distractor_meta FROM tasks_master;")
master_tasks = {}
for r in cur_c.fetchall():
    master_tasks[r[0]] = {
        'id': r[0],
        'qtext': r[1],
        'qlatex': r[2],
        'correct_answer': r[3],
        'calatex': r[4],
        'dmeta': r[5] if r[5] else []
    }

# Sanitization helper
def clean_str(s):
    if not isinstance(s, str) or not s:
        return s
    s = re.sub(r'\\dfrac\{([^}]+)\}\{\$([^$]+)\$\}', r'\\dfrac{\1}{\2}', s)
    s = re.sub(r'\\dfrac\{\$([^$]+)\$\}\{([^}]+)\}', r'\\dfrac{\1}{\2}', s)
    s = re.sub(r'\\frac\{([^}]+)\}\{\$([^$]+)\$\}', r'\\frac{\1}{\2}', s)
    s = re.sub(r'\\frac\{\$([^$]+)\$\}\{([^}]+)\}', r'\\frac{\1}{\2}', s)
    s = re.sub(r'\\Deltax\b', r'\\Delta x', s)
    s = re.sub(r'\\quad([a-zA-Z])', r'\\quad \1', s)
    s = re.sub(r'\$x\^\{(\d+)\}\$', r'x^{\1}', s)
    s = re.sub(r'\$x\^(\d+)\$', r'x^{\1}', s)
    return s

def clean_obj(obj):
    if isinstance(obj, str):
        return clean_str(obj)
    elif isinstance(obj, list):
        return [clean_obj(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: clean_obj(v) for k, v in obj.items()}
    return obj

# Fetch reports
cur_d.execute("SELECT id, session_id, report_json FROM diag_reports;")
reports = cur_d.fetchall()

updated = 0
for rid, sid, rjson in reports:
    if isinstance(rjson, str):
        rjson = json.loads(rjson)
    
    # Fetch all diag_answers for this session_id
    cur_d.execute("SELECT task_id, student_answer, eval_category, skill_id FROM diag_answers WHERE session_id = %s;", (sid,))
    diag_answers = cur_d.fetchall()
    
    # A skill is tested more than once during a diagnostic.  task_id is the
    # only stable join key for a report error entry; never choose an arbitrary
    # answer by skill_id.
    answers_by_task = {a[0]: a for a in diag_answers}
    
    error_patterns = rjson.get('error_patterns', [])
    new_error_patterns = []
    
    for ep in error_patterns:
        task_id = ep.get('task_id')
        ans = answers_by_task.get(task_id)
        # Old reports without task_id cannot be rehydrated safely.  Leave them
        # untouched instead of attaching a different task with the same skill.
        if not ans:
            new_error_patterns.append(clean_obj(ep))
            continue
        task_id = ans[0] if ans else None
        
        mt = master_tasks.get(task_id) if task_id else None
        
        if mt:
            ep['task_id'] = task_id
            ep['question_text'] = mt['qtext']
            ep['question_latex'] = clean_str(mt['qlatex']) if mt['qlatex'] else None
            
            # Rebuild options
            new_opts = []
            new_opts_latex = []
            correct = mt.get('correct_answer')
            if correct:
                new_opts.append(clean_str(correct))
                new_opts_latex.append(clean_str(mt['calatex'] or correct))
            for dm in mt['dmeta']:
                if isinstance(dm, dict):
                    v = clean_str(dm.get('value'))
                    if v and v not in new_opts:
                        new_opts.append(v)
                        new_opts_latex.append(clean_str(dm.get('value_latex') or v))
            if new_opts:
                ep['answer_options'] = new_opts
                ep['answer_options_latex'] = new_opts_latex
            ep['correct_answer'] = correct
            ep['correct_answer_latex'] = clean_str(mt['calatex'] or correct) if correct else None
                
            # Rebuild distractor explanation
            st_ans = ep.get('student_answer') or (ans[1] if ans else None)
            if st_ans and mt['dmeta']:
                def norm_s(s): return (s or '').replace('$', '').replace(' ', '').lower().strip()
                st_norm = norm_s(st_ans)
                for dm in mt['dmeta']:
                    if isinstance(dm, dict):
                        dv = norm_s(dm.get('value'))
                        de = clean_str(dm.get('explanation_latex') or dm.get('explanation'))
                        if dv and st_norm and (dv in st_norm or st_norm in dv) and de:
                            ep['distractor_explanation'] = de
                            break
        else:
            # Fallback sanitization for unmapped items
            ep = clean_obj(ep)
            
        new_error_patterns.append(ep)
        
    rjson['error_patterns'] = new_error_patterns
    rjson = clean_obj(rjson)
    
    cur_d.execute("UPDATE diag_reports SET report_json = %s::jsonb WHERE id = %s;", (json.dumps(rjson, ensure_ascii=False), rid))
    updated += 1

conn_d.commit()
print(f"Successfully rehydrated & fully restored all {updated} diagnostic reports by exact task_id!")
