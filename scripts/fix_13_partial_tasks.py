import asyncio
import sys
import json
import psycopg2

sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service/scripts')
from backfill_latex_deepseek import process_task, field_is_acceptable, validate_with_katex

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

cur.execute("SELECT id, question_text, correct_answer, distractor_meta, question_latex, correct_answer_latex FROM tasks_master")
rows = cur.fetchall()

invalid_ids = []
for r in rows:
    tid, qt, ca, dm, ql, cal = r[0], r[1], r[2], r[3], r[4], r[5]
    all_ok = True
    if ql:
        ok, _ = validate_with_katex(ql)
        if not ok: all_ok = False
    if cal:
        ok, _ = validate_with_katex(cal)
        if not ok: all_ok = False
    for d in (dm or []):
        if isinstance(d, dict):
            if d.get('value_latex'):
                ok, _ = validate_with_katex(d['value_latex'])
                if not ok: all_ok = False
            if d.get('explanation_latex'):
                ok, _ = validate_with_katex(d['explanation_latex'])
                if not ok: all_ok = False
    if not all_ok:
        invalid_ids.append(tid)

print(f"Found {len(invalid_ids)} tasks in tasks_master with KaTeX errors: {invalid_ids}")

async def main():
    semaphore = asyncio.Semaphore(2)
    for tid in invalid_ids:
        cur.execute("SELECT question_text, correct_answer, distractor_meta FROM tasks_master WHERE id = %s", (tid,))
        r = cur.fetchone()
        if not r: continue
        qt, ca, dm_json = r[0], r[1], r[2]
        
        print(f"=== DeepSeek fixing task: {tid} ===")
        res = await process_task(tid, qt, ca, dm_json, semaphore)
        field_results = res['field_results']
        dmeta_obj = json.loads(dm_json) if isinstance(dm_json, str) else (dm_json or [])
        
        new_ql = None
        if 'question' in field_results and field_is_acceptable(field_results['question']):
            new_ql = field_results['question']['canonical']
        elif qt:
            new_ql = qt
            
        new_cal = None
        if 'answer' in field_results and field_is_acceptable(field_results['answer']):
            new_cal = field_results['answer']['canonical']
        elif ca:
            new_cal = ca
            
        for k, v in field_results.items():
            if k.startswith('dmeta[') and field_is_acceptable(v):
                import re
                m = re.match(r'dmeta\[(\d+)\]\.(.+)', k)
                if m:
                    idx = int(m.group(1))
                    field = m.group(2)
                    if idx < len(dmeta_obj) and isinstance(dmeta_obj[idx], dict):
                        dmeta_obj[idx][f'{field}_latex'] = v['canonical']
                    
        cur.execute('''
            UPDATE tasks_master
            SET question_latex = %s,
                correct_answer_latex = %s,
                distractor_meta = %s::jsonb,
                latex_status = 'verified',
                latex_normalized_at = NOW()
            WHERE id = %s
        ''', (new_ql, new_cal, json.dumps(dmeta_obj, ensure_ascii=False), tid))
        conn.commit()
        print(f"Fixed and verified {tid}!")

if __name__ == '__main__':
    asyncio.run(main())
