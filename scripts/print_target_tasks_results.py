import psycopg2
import json

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

TARGET_IDS = [
    'G11_TB_§5_5_54',
    'ds_llm_fa538615ad37',
    'G8_TB_28_671.2',
    'G7_ALG_28_1'
]

for tid in TARGET_IDS:
    cur.execute('SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, distractor_meta FROM tasks_master WHERE id = %s;', (tid,))
    row = cur.fetchone()
    if row:
        print('='*60)
        print(f'=== TASK ID: {row[0]} ===')
        print('Условие (question_text):        ', row[1])
        print('Условие LaTeX (question_latex): ', row[2])
        print('Ответ (correct_answer):         ', row[3])
        print('Ответ LaTeX (correct_answer_latex):', row[4])
        print('Дистракторы и описания (distractor_meta):')
        print(json.dumps(row[5], indent=2, ensure_ascii=False))
        print()
