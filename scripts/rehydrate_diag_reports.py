import psycopg2
import json

conn_c = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
conn_d = psycopg2.connect(dbname='algo_diagnostic', user='algo', password='algo_password', host='127.0.0.1', port=5433)
cur_c = conn_c.cursor()
cur_d = conn_d.cursor()

# Get all tasks from content
cur_c.execute("SELECT id, question_text, question_latex, correct_answer_latex, distractor_meta FROM tasks_master")
tasks = {}
for r in cur_c.fetchall():
    tasks[r[0]] = {
        'question_text': r[1],
        'question_latex': r[2],
        'correct_answer_latex': r[3],
        'distractor_meta': r[4] if r[4] else []
    }

# Update all diag reports
cur_d.execute("SELECT id, session_id, report_json FROM diag_reports")
reports = cur_d.fetchall()

updated_count = 0
for rid, sid, rjson in reports:
    if isinstance(rjson, str):
        rjson = json.loads(rjson)
    
    # get session tasks to map accurately
    cur_d.execute("SELECT task_id FROM diag_answers WHERE session_id = %s", (sid,))
    session_tasks = [row[0] for row in cur_d.fetchall()]
    
    changed = False
    for ep in rjson.get('error_patterns', []):
        sk_id = ep.get('skill_id') # Usually this is the task_id!
        if sk_id in tasks:
            tdata = tasks[sk_id]
            if tdata['question_latex']:
                ep['question_latex'] = tdata['question_latex']
                ep['question_text'] = tdata['question_latex'] # OVERRIDE TEXT WITH LATEX FOR FRONTEND!
                changed = True
            
            # options
            new_opts = []
            if tdata['correct_answer_latex']:
                new_opts.append(tdata['correct_answer_latex'])
                
            for dm in tdata['distractor_meta']:
                if isinstance(dm, dict):
                    val = dm.get('value_latex') or dm.get('value')
                    if val:
                        new_opts.append(val)
            
            if new_opts and len(new_opts) > 1:
                ep['answer_options'] = new_opts
                changed = True
                
    if changed:
        cur_d.execute("UPDATE diag_reports SET report_json = %s::jsonb WHERE id = %s", (json.dumps(rjson, ensure_ascii=False), rid))
        updated_count += 1

conn_d.commit()
print(f"Re-hydrated {updated_count} reports.")
