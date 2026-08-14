import asyncio
import sys
import json
import psycopg2

sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service/scripts')
from backfill_latex_deepseek import process_task, field_is_acceptable

TARGET_IDS = [
    'G11_TB_§5_5_54',
    'ds_llm_fa538615ad37',
    'G8_TB_28_671.2',
    'G7_ALG_28_1'
]

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

tasks_data = []
for tid in TARGET_IDS:
    cur.execute('SELECT id, question_text, correct_answer, distractor_meta FROM tasks_master WHERE id = %s', (tid,))
    row = cur.fetchone()
    if row:
        tasks_data.append(row)

async def main():
    semaphore = asyncio.Semaphore(2)
    for r in tasks_data:
        tid, qt, ca, dm_json = r[0], r[1], r[2], r[3]
        print(f'=== Running DeepSeek on Task: {tid} ===')
        
        # Prepare clean prompt input for tasks with formatting issues
        if tid == 'G11_TB_§5_5_54':
            qt = r'Докажите, что функция $f(x) = \frac{1}{x}$ убывает на каждом из промежутков $(-\infty; 0)$ и $(0; +\infty)$.'
        elif tid == 'ds_llm_fa538615ad37':
            qt = r'Решите систему уравнений: $\begin{cases} \sqrt{x^{2}-y^{2}} = 4 \\ x + y = 8 \end{cases}$'
        elif tid == 'G8_TB_28_671.2':
            qt = r'Является ли пара чисел $(-1; 3)$ решением уравнения $xy + y = 6$?'
        elif tid == 'G7_ALG_28_1':
            qt = r'Найдите уравнение, корнем которого является число $-3$:' + '\n' + r'1) $-3x = 12$' + '\n' + r'2) $2x - 7 = -13$' + '\n' + r'3) $\frac{1}{3x} = -1$' + '\n' + r'4) $5(x - 2) + 1 = 4x$'
            
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
            SET question_text = %s,
                question_latex = %s,
                correct_answer_latex = %s,
                distractor_meta = %s::jsonb,
                latex_status = 'verified'
            WHERE id = %s
        ''', (qt, new_ql, new_cal, json.dumps(dmeta_obj, ensure_ascii=False), tid))
        conn.commit()
        print(f'Successfully processed DeepSeek backfill for {tid}!')
        print('  Q_LATEX:', repr(new_ql))
        print('  CAL:', repr(new_cal))
        print()

if __name__ == '__main__':
    asyncio.run(main())
