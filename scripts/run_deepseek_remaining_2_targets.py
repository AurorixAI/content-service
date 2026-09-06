import asyncio
import sys
import json
import psycopg2

sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service/scripts')
from backfill_latex_deepseek import process_task, field_is_acceptable, validate_with_katex

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

found_tasks = []

# Task 3: дописал x к каждому
cur.execute("SELECT id, question_text, correct_answer, distractor_meta FROM tasks_master WHERE distractor_meta::text LIKE '%дописал x к каждому%' LIMIT 1;")
r3 = cur.fetchone()
if r3: found_tasks.append(r3)

# Task 4: y = x^2 - 4x
cur.execute("SELECT id, question_text, correct_answer, distractor_meta FROM tasks_master WHERE question_text LIKE '%x^{2}-4x%' OR question_text LIKE '%x^2-4x%' LIMIT 1;")
r4 = cur.fetchone()
if r4: found_tasks.append(r4)

print(f"Found {len(found_tasks)} target tasks:")
for t in found_tasks:
    print(f"  - ID: {t[0]:<25} Q: {repr(t[1])[:80]}")

async def main():
    semaphore = asyncio.Semaphore(2)
    for tid, qt, ca, dm_json in found_tasks:
        print("\n" + "="*70)
        print(f"=== PROCESSING DEEPSEEK FOR TASK: {tid} ===")
        print(f"BEFORE Q_TEXT: {repr(qt)}")
        
        res = await process_task(tid, qt, ca, dm_json, semaphore)
        field_results = res['field_results']
        dmeta_obj = json.loads(dm_json) if isinstance(dm_json, str) else (dm_json or [])
        
        new_ql = field_results['question']['canonical'] if 'question' in field_results and field_is_acceptable(field_results['question']) else qt
        new_cal = field_results['answer']['canonical'] if 'answer' in field_results and field_is_acceptable(field_results['answer']) else ca
        
        for k, v in field_results.items():
            if k.startswith('dmeta[') and field_is_acceptable(v):
                import re
                m = re.match(r'dmeta\[(\d+)\]\.(.+)', k)
                if m:
                    idx = int(m.group(1))
                    field = m.group(2)
                    if idx < len(dmeta_obj) and isinstance(dmeta_obj[idx], dict):
                        dmeta_obj[idx][f'{field}_latex'] = v['canonical']
                        dmeta_obj[idx][field] = v['canonical']

        import re
        def clean_s(s):
            if not s: return s
            s = re.sub(r'\\dfrac\{([^}]+)\}\{\$([^$]+)\$\}', r'\\dfrac{\1}{\2}', s)
            s = re.sub(r'\\dfrac\{\$([^$]+)\$\}\{([^}]+)\}', r'\\dfrac{\1}{\2}', s)
            s = re.sub(r'\\Deltax\b', r'\\Delta x', s)
            s = re.sub(r'\\quad([a-zA-Z])', r'\\quad \1', s)
            return s

        new_ql = clean_s(new_ql)
        new_cal = clean_s(new_cal)
        for d in dmeta_obj:
            if isinstance(d, dict):
                for fk in ['value', 'value_latex', 'explanation', 'explanation_latex', 'error_logic', 'error_logic_latex']:
                    if d.get(fk):
                        d[fk] = clean_s(d[fk])

        print(f"AFTER Q_LATEX:   {repr(new_ql)}")
        print(f"AFTER C_ANS_LATEX: {repr(new_cal)}")
        print("AFTER DMETA:")
        for idx, d in enumerate(dmeta_obj):
            if isinstance(d, dict):
                print(f"  [{idx}] val_latex: {repr(d.get('value_latex'))}")
                print(f"      exp_latex: {repr(d.get('explanation_latex'))}")

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
        print(f"Saved & set latex_status = 'verified' for {tid}!")

if __name__ == '__main__':
    asyncio.run(main())
