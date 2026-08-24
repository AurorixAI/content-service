"""
Synchronize distractor explanations for all diagnostic sessions in algo_diagnostic from tasks_master in algo_content.
"""
import psycopg2
import json
import re

def norm(s):
    if not s: return ''
    s = re.sub(r'\\text\{[^}]*\}', '', str(s))
    s = re.sub(r'[\$\s\\\(\)\{\}\[\]\.,:;]', '', s).lower()
    return s

def sync_explanations():
    print("Connecting to databases...")
    conn_c = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
    cur_c = conn_c.cursor()

    conn_d = psycopg2.connect(dbname='algo_diagnostic', user='algo', password='algo_password', host='127.0.0.1', port=5433)
    cur_d = conn_d.cursor()

    # Fetch all tasks and their distractor_meta
    cur_c.execute("SELECT id, distractor_meta, answer_options, answer_options_latex FROM tasks_master;")
    task_map = {}
    for tid, d_meta, opts, opts_l in cur_c.fetchall():
        task_map[tid] = {
            'distractors': d_meta or [],
            'options': opts or [],
            'options_latex': opts_l or opts or []
        }

    cur_d.execute("SELECT session_id, report_json FROM diag_reports WHERE report_json IS NOT NULL;")
    reports = cur_d.fetchall()

    for session_id, rj_raw in reports:
        rj = rj_raw if isinstance(rj_raw, dict) else json.loads(rj_raw)
        modified = False

        if 'error_patterns' in rj and isinstance(rj['error_patterns'], list):
            for ep in rj['error_patterns']:
                tid = ep.get('task_id')
                student_ans = ep.get('student_answer')
                t_info = task_map.get(tid)
                if not t_info:
                    continue

                best_expl = None
                for d in t_info['distractors']:
                    d_val = d.get('value') or d.get('value_latex') or ''
                    if norm(d_val) == norm(student_ans) or (norm(student_ans) and norm(student_ans) in norm(d_val)) or (norm(d_val) and norm(d_val) in norm(student_ans)):
                        best_expl = d.get('explanation') or d.get('error_logic') or d.get('error_logic_latex')
                        break

                if best_expl:
                    ep['eval_category'] = 'distractor'
                    ep['distractor_explanation'] = best_expl
                    ep['distractor_explanation_latex'] = best_expl
                    modified = True
                    print(f"Synced [{session_id[:8]}] {tid}: {best_expl[:60]}...")

        if modified:
            cur_d.execute(
                "UPDATE diag_reports SET report_json = %s WHERE session_id = %s;",
                (json.dumps(rj, ensure_ascii=False), session_id)
            )
            # Also update diag_answers eval_category to 'distractor'
            for ep in rj['error_patterns']:
                if ep.get('eval_category') == 'distractor':
                    cur_d.execute(
                        "UPDATE diag_answers SET eval_category = 'distractor' WHERE session_id = %s AND task_id = %s;",
                        (session_id, ep.get('task_id'))
                    )

    conn_d.commit()
    conn_c.close()
    conn_d.close()
    print("Sync completed successfully!")

if __name__ == '__main__':
    sync_explanations()
