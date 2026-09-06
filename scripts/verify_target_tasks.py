import psycopg2
import json

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

for tid in ['G11_TB_6_10*_6_83_б', 'G11_TB_§4_3']:
    cur.execute('SELECT id, question_text, question_latex, correct_answer_latex, distractor_meta FROM tasks_master WHERE id = %s;', (tid,))
    row = cur.fetchone()
    print(f'=== TASK: {tid} ===')
    print('question_text:', row[1])
    print('question_latex:', row[2])
    print('correct_answer_latex:', row[3])
    print('distractor_meta:', json.dumps(row[4], indent=2, ensure_ascii=False))
    print()
