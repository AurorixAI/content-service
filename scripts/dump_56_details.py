import psycopg2, os, json
from scripts.backfill_latex_deepseek import final_display_issues

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('''
    SELECT tm.id, tm.is_active,
           tm.question_text, tm.question_latex,
           tm.correct_answer, tm.correct_answer_latex,
           tm.distractor_meta, tm.answer_options, tm.answer_options_latex
    FROM tasks_master tm
    WHERE tm.latex_status = 'partial'
    ORDER BY tm.id
''')
rows = cur.fetchall()

print(f'Total partial: {len(rows)}')
tasks = []
for row in rows:
    tid, active, q, q_l, a, a_l, dmeta, opts, opts_l = row
    dmeta = dmeta if isinstance(dmeta, list) else []
    opts = opts if isinstance(opts, list) else []
    opts_l = opts_l if isinstance(opts_l, list) else []
    issues, req = final_display_issues(q, q_l, a, a_l, dmeta, opts, opts_l)
    
    # Collect details of failing fields
    field_details = {}
    for fld, info in issues.items():
        reason = info.get('reason', '')
        if fld == 'question':
            field_details[fld] = {'reason': reason, 'raw': q, 'ltx': q_l}
        elif fld == 'answer':
            field_details[fld] = {'reason': reason, 'raw': a, 'ltx': a_l}
        elif fld.startswith('dmeta['):
            idx = int(fld.split('[')[1].split(']')[0])
            part = fld.split('.')[1]
            d = dmeta[idx]
            if part == 'value':
                field_details[fld] = {'reason': reason, 'raw': d.get('value'), 'ltx': d.get('value_latex')}
            else:
                s_key = 'error_logic' if d.get('error_logic') else 'explanation'
                d_key = 'error_logic_latex' if d.get('error_logic_latex') else 'explanation_latex'
                field_details[fld] = {'reason': reason, 'raw': d.get(s_key), 'ltx': d.get(d_key)}
        elif fld.startswith('option['):
            idx = int(fld.split('[')[1].split(']')[0])
            field_details[fld] = {'reason': reason, 'raw': opts[idx] if idx < len(opts) else None, 'ltx': opts_l[idx] if idx < len(opts_l) else None}
            
    tasks.append({
        'id': tid,
        'active': active,
        'issues': field_details
    })

with open('/tmp/failing_56_details.json', 'w') as f:
    json.dump(tasks, f, indent=2, ensure_ascii=False)

print('Saved /tmp/failing_56_details.json successfully')
