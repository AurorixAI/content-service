import psycopg2, json

conn = psycopg2.connect('postgresql://algo:algo_password@localhost:5433/algo_diagnostic')
cur = conn.cursor()
cur.execute('SELECT id, report_json FROM diag_reports;')
rows = cur.fetchall()

for rep_id, rep in rows:
    if not rep or not isinstance(rep, dict): continue
    eps = rep.get('error_patterns') or []
    for i, ep in enumerate(eps):
        q = ep.get('question_text') or ''
        s = json.dumps(ep, ensure_ascii=False)
        
        # Screenshot 1: №19 "Какие из чисел -3, -2, 0, 1 являются корнями уравнения? x^2 - 5x + 4 = 0"
        if '-5x + 4 = 0' in s or '- 5x + 4 = 0' in s or 'x² - 5x + 4 = 0' in s or 'x^2 - 5x + 4 = 0' in s or ('-3, -2, 0, 1' in s and '5x' in s):
            print(f'=== SCREENSHOT 1: Rep {rep_id}, idx {i+1} ===')
            print('task_id:', ep.get('task_id'))
            print('question_text:', q)
            print('correct_answer:', ep.get('correct_answer'))
            print('correct_answer_latex:', ep.get('correct_answer_latex'))
            print('student_answer:', ep.get('student_answer'))
            print('options:', ep.get('answer_options'))
            print('options_latex:', ep.get('answer_options_latex'))
            print('distractor_exp:', ep.get('distractor_explanation'))

        # Screenshot 2: №2 "sin 420"
        if '420' in s:
            print(f'=== SCREENSHOT 2: Rep {rep_id}, idx {i+1} ===')
            print('task_id:', ep.get('task_id'))
            print('question_text:', q)
            print('correct_answer:', ep.get('correct_answer'))
            print('correct_answer_latex:', ep.get('correct_answer_latex'))
            print('student_answer:', ep.get('student_answer'))
            print('options:', ep.get('answer_options'))
            print('options_latex:', ep.get('answer_options_latex'))
            print('distractor_exp:', ep.get('distractor_explanation'))

        # Screenshot 3: №16 "Решите неравенство: x^2 < 0"
        if 'x^2 < 0' in s or 'x² < 0' in s or 'x < \\sqrt{0}' in s or 'квадрат числа не может быть отрицательным' in s:
            print(f'=== SCREENSHOT 3: Rep {rep_id}, idx {i+1} ===')
            print('task_id:', ep.get('task_id'))
            print('question_text:', q)
            print('correct_answer:', ep.get('correct_answer'))
            print('correct_answer_latex:', ep.get('correct_answer_latex'))
            print('student_answer:', ep.get('student_answer'))
            print('options:', ep.get('answer_options'))
            print('options_latex:', ep.get('answer_options_latex'))
            print('distractor_exp:', ep.get('distractor_explanation'))
