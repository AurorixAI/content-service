"""
Apply surgical fixes for Task 19, Task 20, related system inequality tasks in tasks_master,
and historical diagnostic answers / report snapshots in algo_diagnostic.
"""
import psycopg2
import json

def update_content_db():
    print("Connecting to algo_content DB (port 5434)...")
    conn = psycopg2.connect(
        dbname='algo_content',
        user='algo',
        password='algo_password',
        host='127.0.0.1',
        port=5434
    )
    cur = conn.cursor()

    content_updates = [
        # Task 19: ds_llm_c785cae26c32
        {
            'id': 'ds_llm_c785cae26c32',
            'question_text': 'Решите систему неравенств и запишите множество решений в виде объединения промежутков: $\\begin{cases} x^2 - 5x + 6 > 0 \\\\ x^2 - 9 \\le 0 \\end{cases}$',
            'question_latex': 'Решите систему неравенств и запишите множество решений в виде объединения промежутков: $\\begin{cases} x^{2} - 5x + 6 > 0 \\\\ x^{2} - 9 \\le 0 \\end{cases}$',
            'answer_type': 'multiple_choice',
            'correct_answer': '$[-3; 2)$',
            'correct_answer_latex': '$[-3; 2)$',
            'answer_options': ['$[-3; 2)$', '$[-3; 2) \\cup (3; +\\infty)$', '$(-\\infty; 2) \\cup (3; +\\infty)$', '$[-3; 3]$'],
            'answer_options_latex': ['$[-3; 2)$', '$[-3; 2) \\cup (3; +\\infty)$', '$(-\\infty; 2) \\cup (3; +\\infty)$', '$[-3; 3]$'],
            'distractor_meta': [
                {
                    'value': '$[-3; 2) \\cup (3; +\\infty)$',
                    'value_latex': '$[-3; 2) \\cup (3; +\\infty)$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик не ограничил решение сверху отрезком $[-3; 3]$ и включил весь правый луч.'
                },
                {
                    'value': '$(-\\infty; 2) \\cup (3; +\\infty)$',
                    'value_latex': '$(-\\infty; 2) \\cup (3; +\\infty)$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик нашёл решение только первого неравенства, проигнорировав второе неравенство.'
                },
                {
                    'value': '$[-3; 3]$',
                    'value_latex': '$[-3; 3]$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик нашёл решение только второго неравенства, проигнорировав первое.'
                }
            ],
            'latex_status': 'verified',
            'verification_status': 'verified'
        },
        # Duplicates of Task 19
        {
            'id': 'ds_llm_60037f9fcb95',
            'question_text': 'Решите систему неравенств и запишите множество решений в виде объединения промежутков: $\\begin{cases} x^2 - 5x + 6 > 0 \\\\ x^2 - 9 \\le 0 \\end{cases}$',
            'question_latex': 'Решите систему неравенств и запишите множество решений в виде объединения промежутков: $\\begin{cases} x^{2} - 5x + 6 > 0 \\\\ x^{2} - 9 \\le 0 \\end{cases}$',
            'answer_type': 'multiple_choice',
            'correct_answer': '$[-3; 2)$',
            'correct_answer_latex': '$[-3; 2)$',
            'answer_options': ['$[-3; 2)$', '$[-3; 2) \\cup (3; +\\infty)$', '$(-\\infty; 2) \\cup (3; +\\infty)$', '$[-3; 3]$'],
            'answer_options_latex': ['$[-3; 2)$', '$[-3; 2) \\cup (3; +\\infty)$', '$(-\\infty; 2) \\cup (3; +\\infty)$', '$[-3; 3]$'],
            'distractor_meta': [
                {
                    'value': '$[-3; 2) \\cup (3; +\\infty)$',
                    'value_latex': '$[-3; 2) \\cup (3; +\\infty)$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик не ограничил решение сверху отрезком $[-3; 3]$ и включил весь правый луч.'
                },
                {
                    'value': '$(-\\infty; 2) \\cup (3; +\\infty)$',
                    'value_latex': '$(-\\infty; 2) \\cup (3; +\\infty)$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик нашёл решение только первого неравенства, проигнорировав второе неравенство.'
                },
                {
                    'value': '$[-3; 3]$',
                    'value_latex': '$[-3; 3]$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик нашёл решение только второго неравенства, проигнорировав первое.'
                }
            ],
            'latex_status': 'verified',
            'verification_status': 'verified'
        },
        {
            'id': 'ds_llm_14ad1e5352c3',
            'question_text': 'Решите систему неравенств и запишите множество решений в виде объединения промежутков: $\\begin{cases} x^2 - 5x + 6 > 0 \\\\ x^2 - 9 \\le 0 \\end{cases}$',
            'question_latex': 'Решите систему неравенств и запишите множество решений в виде объединения промежутков: $\\begin{cases} x^{2} - 5x + 6 > 0 \\\\ x^{2} - 9 \\le 0 \\end{cases}$',
            'answer_type': 'multiple_choice',
            'correct_answer': '$[-3; 2)$',
            'correct_answer_latex': '$[-3; 2)$',
            'answer_options': ['$[-3; 2)$', '$[-3; 2) \\cup (3; +\\infty)$', '$(-\\infty; 2) \\cup (3; +\\infty)$', '$[-3; 3]$'],
            'answer_options_latex': ['$[-3; 2)$', '$[-3; 2) \\cup (3; +\\infty)$', '$(-\\infty; 2) \\cup (3; +\\infty)$', '$[-3; 3]$'],
            'distractor_meta': [
                {
                    'value': '$[-3; 2) \\cup (3; +\\infty)$',
                    'value_latex': '$[-3; 2) \\cup (3; +\\infty)$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик не ограничил решение сверху отрезком $[-3; 3]$ и включил весь правый луч.'
                },
                {
                    'value': '$(-\\infty; 2) \\cup (3; +\\infty)$',
                    'value_latex': '$(-\\infty; 2) \\cup (3; +\\infty)$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик нашёл решение только первого неравенства, проигнорировав второе неравенство.'
                },
                {
                    'value': '$[-3; 3]$',
                    'value_latex': '$[-3; 3]$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик нашёл решение только второго неравенства, проигнорировав первое.'
                }
            ],
            'latex_status': 'verified',
            'verification_status': 'verified'
        },
        {
            'id': 'ds_llm_936d42bb0c1b',
            'question_text': 'Решите систему неравенств и запишите множество решений в виде объединения промежутков: $\\begin{cases} x^2 - 4x - 5 \\ge 0 \\\\ x^2 - 2x - 8 < 0 \\end{cases}$',
            'question_latex': 'Решите систему неравенств и запишите множество решений в виде объединения промежутков: $\\begin{cases} x^{2} - 4x - 5 \\ge 0 \\\\ x^{2} - 2x - 8 < 0 \\end{cases}$',
            'answer_type': 'multiple_choice',
            'correct_answer': '$(-2; -1]$',
            'correct_answer_latex': '$(-2; -1]$',
            'answer_options': ['$(-2; -1]$', '$(-2; -1] \\cup [5; 4)$', '$(-\\infty; -1] \\cup [5; +\\infty)$', '$(-2; 4)$'],
            'answer_options_latex': ['$(-2; -1]$', '$(-2; -1] \\cup [5; 4)$', '$(-\\infty; -1] \\cup [5; +\\infty)$', '$(-2; 4)$'],
            'distractor_meta': [
                {
                    'value': '$(-2; -1] \\cup [5; 4)$',
                    'value_latex': '$(-2; -1] \\cup [5; 4)$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик формально записал объединение пересечений, не заметив, что $[5; 4)$ — пустое множество.'
                },
                {
                    'value': '$(-\\infty; -1] \\cup [5; +\\infty)$',
                    'value_latex': '$(-\\infty; -1] \\cup [5; +\\infty)$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик решил только первое неравенство, проигнорировав второе.'
                },
                {
                    'value': '$(-2; 4)$',
                    'value_latex': '$(-2; 4)$',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик решил только второе неравенство, проигнорировав первое.'
                }
            ],
            'latex_status': 'verified',
            'verification_status': 'verified'
        },
        # Task 20 family: G9_TB_24_461.1..4
        {
            'id': 'G9_TB_24_461.1',
            'question_text': 'Является ли пара чисел $(4; 2)$ решением системы неравенств: $\\begin{cases} x^2 - 2y > 7 \\\\ 3x + y > 3 \\end{cases}$?',
            'question_latex': 'Является ли пара чисел $(4; 2)$ решением системы неравенств: $\\begin{cases} x^{2} - 2y > 7 \\\\ 3x + y > 3 \\end{cases}$?',
            'answer_type': 'multiple_choice',
            'correct_answer': 'да',
            'correct_answer_latex': 'да',
            'answer_options': ['да', 'нет', 'да, только для первого неравенства', 'да, только для второго неравенства'],
            'answer_options_latex': ['да', 'нет', 'да, только для первого неравенства', 'да, только для второго неравенства'],
            'distractor_meta': [
                {
                    'value': 'нет',
                    'value_latex': 'нет',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик ошибся в проверке второго неравенства.'
                },
                {
                    'value': 'да, только для первого неравенства',
                    'value_latex': 'да, только для первого неравенства',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик посчитал, что второе неравенство не выполнено.'
                },
                {
                    'value': 'да, только для второго неравенства',
                    'value_latex': 'да, только для второго неравенства',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик посчитал, что первое неравенство не выполнено.'
                }
            ],
            'latex_status': 'verified',
            'verification_status': 'verified'
        },
        {
            'id': 'G9_TB_24_461.2',
            'question_text': 'Является ли пара чисел $(-5; 1)$ решением системы неравенств: $\\begin{cases} x^2 - 2y > 7 \\\\ 3x + y > 3 \\end{cases}$?',
            'question_latex': 'Является ли пара чисел $(-5; 1)$ решением системы неравенств: $\\begin{cases} x^{2} - 2y > 7 \\\\ 3x + y > 3 \\end{cases}$?',
            'answer_type': 'multiple_choice',
            'correct_answer': 'нет',
            'correct_answer_latex': 'нет',
            'answer_options': ['нет', 'да', 'да, только для первого неравенства', 'да, только для второго неравенства'],
            'answer_options_latex': ['нет', 'да', 'да, только для первого неравенства', 'да, только для второго неравенства'],
            'distractor_meta': [
                {
                    'value': 'да',
                    'value_latex': 'да',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик посчитал $-14 > 3$ верным или ошибся в знаках.'
                },
                {
                    'value': 'да, только для первого неравенства',
                    'value_latex': 'да, только для первого неравенства',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик правильно проверил неравенства, но не сформулировал общий ответ системы.'
                },
                {
                    'value': 'да, только для второго неравенства',
                    'value_latex': 'да, только для второго неравенства',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик ошибочно решил, что второе неравенство выполняется.'
                }
            ],
            'latex_status': 'verified',
            'verification_status': 'verified'
        },
        {
            'id': 'G9_TB_24_461.3',
            'question_text': 'Является ли пара чисел $(-2; -1)$ решением системы неравенств: $\\begin{cases} x^2 - 2y > 7 \\\\ 3x + y > 3 \\end{cases}$?',
            'question_latex': 'Является ли пара чисел $(-2; -1)$ решением системы неравенств: $\\begin{cases} x^{2} - 2y > 7 \\\\ 3x + y > 3 \\end{cases}$?',
            'answer_type': 'multiple_choice',
            'correct_answer': 'нет',
            'correct_answer_latex': 'нет',
            'answer_options': ['нет', 'да', 'да, только для первого неравенства', 'да, только для второго неравенства'],
            'answer_options_latex': ['нет', 'да', 'да, только для первого неравенства', 'да, только для второго неравенства'],
            'distractor_meta': [
                {
                    'value': 'да',
                    'value_latex': 'да',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик ошибся в знаках при подстановке отрицательных чисел.'
                },
                {
                    'value': 'да, только для первого неравенства',
                    'value_latex': 'да, только для первого неравенства',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик посчитал $(-2)^2 - 2(-1) = 4 - 2 = 2$ или посчитал $6 > 7$.'
                },
                {
                    'value': 'да, только для второго неравенства',
                    'value_latex': 'да, только для второго неравенства',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик посчитал $3(-2) + (-1) = -6 + 1 = -5 > 3$ или спутал знак минус с плюсом.'
                }
            ],
            'latex_status': 'verified',
            'verification_status': 'verified'
        },
        {
            'id': 'G9_TB_24_461.4',
            'question_text': 'Является ли пара чисел $(6; -5)$ решением системы неравенств: $\\begin{cases} x^2 - 2y > 7 \\\\ 3x + y > 3 \\end{cases}$?',
            'question_latex': 'Является ли пара чисел $(6; -5)$ решением системы неравенств: $\\begin{cases} x^{2} - 2y > 7 \\\\ 3x + y > 3 \\end{cases}$?',
            'answer_type': 'multiple_choice',
            'correct_answer': 'да',
            'correct_answer_latex': 'да',
            'answer_options': ['да', 'нет', 'да, только для первого неравенства', 'да, только для второго неравенства'],
            'answer_options_latex': ['да', 'нет', 'да, только для первого неравенства', 'да, только для второго неравенства'],
            'distractor_meta': [
                {
                    'value': 'нет',
                    'value_latex': 'нет',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик ошибся при подсчете $36 - 2(-5) = 46$ или $18 - 5 = 13$.'
                },
                {
                    'value': 'да, только для первого неравенства',
                    'value_latex': 'да, только для первого неравенства',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик посчитал, что второе неравенство не выполняется.'
                },
                {
                    'value': 'да, только для второго неравенства',
                    'value_latex': 'да, только для второго неравенства',
                    'error_type': 'ai_generated',
                    'error_logic': 'Ученик посчитал, что первое неравенство не выполняется.'
                }
            ],
            'latex_status': 'verified',
            'verification_status': 'verified'
        }
    ]

    for u in content_updates:
        cur.execute('''
            UPDATE tasks_master
            SET question_text = %s,
                question_latex = %s,
                answer_type = %s,
                correct_answer = %s,
                correct_answer_latex = %s,
                answer_options = %s,
                answer_options_latex = %s,
                distractor_meta = %s,
                latex_status = %s,
                verification_status = %s,
                updated_at = NOW()
            WHERE id = %s
        ''', (
            u['question_text'],
            u['question_latex'],
            u['answer_type'],
            u['correct_answer'],
            u['correct_answer_latex'],
            json.dumps(u['answer_options'], ensure_ascii=False),
            json.dumps(u['answer_options_latex'], ensure_ascii=False),
            json.dumps(u['distractor_meta'], ensure_ascii=False),
            u['latex_status'],
            u['verification_status'],
            u['id']
        ))
        print(f"Content DB: Updated {u['id']} ({cur.rowcount} row)")

    conn.commit()
    conn.close()
    print("Content DB updates committed successfully.\n")


def update_diagnostic_history():
    print("Connecting to algo_diagnostic DB (port 5433)...")
    conn = psycopg2.connect(
        dbname='algo_diagnostic',
        user='algo',
        password='algo_password',
        host='127.0.0.1',
        port=5433
    )
    cur = conn.cursor()

    # 1. Update diag_answers historical strings
    # For G9_TB_УПК_811_4: map to the proper distractor string
    cur.execute('''
        UPDATE diag_answers
        SET student_answer = '$(x^2 - 10x + 25) = (x - 5)^2 \\ge 0$, поэтому трёхчлен принимает только положительные значения'
        WHERE task_id = 'G9_TB_УПК_811_4'
          AND student_answer ILIKE '%доказано, что трёхчлен принимает только положительные значения%';
    ''')
    print(f"diag_answers: Updated G9_TB_УПК_811_4 ({cur.rowcount} rows)")

    # For G9_TB_ЗПТ_877: map placeholder "Доказательство: ..." to Option B distractor
    cur.execute('''
        UPDATE diag_answers
        SET student_answer = 'Перенесём всё в левую часть: $(x - y - z)^2 = 0$, откуда $x - y - z = 0$, следовательно, $x = y = z$.'
        WHERE task_id = 'G9_TB_ЗПТ_877'
          AND student_answer ILIKE '%Доказательство%';
    ''')
    print(f"diag_answers: Updated G9_TB_ЗПТ_877 ({cur.rowcount} rows)")

    # For G9_TB_ТЗГ1_1: map '$A$' to '$a = 6$'
    cur.execute('''
        UPDATE diag_answers
        SET student_answer = '$a = 6$'
        WHERE task_id = 'G9_TB_ТЗГ1_1'
          AND student_answer IN ('$A$', 'A', 'a = 6');
    ''')
    print(f"diag_answers: Updated G9_TB_ТЗГ1_1 ({cur.rowcount} rows)")

    # 2. Update report_json snapshots in diag_reports
    cur.execute('''SELECT session_id, report_json FROM diag_reports WHERE report_json IS NOT NULL;''')
    rows = cur.fetchall()
    updated_reports = 0

    for session_id, rj_raw in rows:
        rj = rj_raw if isinstance(rj_raw, dict) else json.loads(rj_raw)
        modified = False

        # Update error_patterns
        if 'error_patterns' in rj and isinstance(rj['error_patterns'], list):
            for ep in rj['error_patterns']:
                tid = ep.get('task_id')
                if tid == 'G9_TB_УПК_811_4':
                    ep['correct_answer'] = '$-(x^2 - 10x + 25) = -(x - 5)^2 \\le 0$ при любых действительных $x$'
                    ep['correct_answer_latex'] = '$-(x^{2} - 10x + 25) = -(x - 5)^{2} \\le 0$ при любых действительных $x$'
                    ep['student_answer'] = '$(x^2 - 10x + 25) = (x - 5)^2 \\ge 0$, поэтому трёхчлен принимает только положительные значения'
                    ep['student_answer_latex'] = '$(x^{2} - 10x + 25) = (x - 5)^{2} \\ge 0$, поэтому трёхчлен принимает только положительные значения'
                    ep['answer_options'] = [
                        '$-(x^2 - 10x + 25) = -(x - 5)^2 \\le 0$ при любых действительных $x$',
                        '$(x^2 - 10x + 25) = (x - 5)^2 \\ge 0$, поэтому трёхчлен принимает только положительные значения',
                        '$-(x^2 + 10x + 25) = -(x + 5)^2 \\le 0$, значение зависит от знака $x$',
                        'При $x = 5$ трёхчлен равен $0$, следовательно, он равен нулю при всех $x$'
                    ]
                    ep['answer_options_latex'] = [
                        '$-(x^{2} - 10x + 25) = -(x - 5)^{2} \\le 0$ при любых действительных $x$',
                        '$(x^{2} - 10x + 25) = (x - 5)^{2} \\ge 0$, поэтому трёхчлен принимает только положительные значения',
                        '$-(x^{2} + 10x + 25) = -(x + 5)^{2} \\le 0$, значение зависит от знака $x$',
                        'При $x = 5$ трёхчлен равен $0$, следовательно, он равен нулю при всех $x$'
                    ]
                    modified = True

                elif tid == 'G9_TB_ЗПТ_877':
                    ep['correct_answer'] = 'Умножим на $2$ и сгруппируем: $(x - y)^2 + (y - z)^2 + (z - x)^2 = 0$. Сумма квадратов равна нулю тогда и только тогда, когда $x - y = 0, y - z = 0, z - x = 0$, откуда $x = y = z$.'
                    ep['correct_answer_latex'] = 'Умножим на $2$ и сгруппируем: $(x - y)^{2} + (y - z)^{2} + (z - x)^{2} = 0$. Сумма квадратов равна нулю тогда и только тогда, когда $x - y = 0, y - z = 0, z - x = 0$, откуда $x = y = z$.'
                    ep['student_answer'] = 'Перенесём всё в левую часть: $(x - y - z)^2 = 0$, откуда $x - y - z = 0$, следовательно, $x = y = z$.'
                    ep['student_answer_latex'] = 'Перенесём всё в левую часть: $(x - y - z)^{2} = 0$, откуда $x - y - z = 0$, следовательно, $x = y = z$.'
                    ep['answer_options'] = [
                        'Умножим на $2$ и сгруппируем: $(x - y)^2 + (y - z)^2 + (z - x)^2 = 0$. Сумма квадратов равна нулю тогда и только тогда, когда $x - y = 0, y - z = 0, z - x = 0$, откуда $x = y = z$.',
                        'Перенесём всё в левую часть: $(x - y - z)^2 = 0$, откуда $x - y - z = 0$, следовательно, $x = y = z$.',
                        'Рассмотрим как квадратное уравнение относительно $x$: его дискриминант $D = 3(y - z)^2 > 0$, значит $x = y = z$.',
                        'Разделим обе части на $(xy + yz + zx)$, откуда получаем $\\frac{x^2+y^2+z^2}{xy+yz+zx} = 1$, что возможно только при $x = y = z = 1$.'
                    ]
                    ep['answer_options_latex'] = [
                        'Умножим на $2$ и сгруппируем: $(x - y)^{2} + (y - z)^{2} + (z - x)^{2} = 0$. Сумма квадратов равна нулю тогда и только тогда, когда $x - y = 0, y - z = 0, z - x = 0$, откуда $x = y = z$.',
                        'Перенесём всё в левую часть: $(x - y - z)^{2} = 0$, откуда $x - y - z = 0$, следовательно, $x = y = z$.',
                        'Рассмотрим как квадратное уравнение относительно $x$: его дискриминант $D = 3(y - z)^{2} > 0$, значит $x = y = z$.',
                        'Разделим обе части на $(xy + yz + zx)$, откуда получаем $\\frac{x^{2}+y^{2}+z^{2}}{xy+yz+zx} = 1$, что возможно только при $x = y = z = 1$.'
                    ]
                    modified = True

                elif tid == 'G9_TB_9_3_г':
                    ep['correct_answer'] = 'Область определения: все действительные числа. График — парабола с вершиной в точке $(0, 0)$, ветви направлены вверх. Функция является чётной, убывает на $(-\\infty; 0]$ и возрастает на $[0; +\\infty)$. Множество значений: $y \\ge 0$.'
                    ep['correct_answer_latex'] = 'Область определения: все действительные числа. График — парабола с вершиной в точке $(0, 0)$, ветви направлены вверх. Функция является чётной, убывает на $(-\\infty; 0]$ и возрастает на $[0; +\\infty)$. Множество значений: $y \\ge 0$.'
                    ep['answer_options'] = [
                        'Область определения: все действительные числа. График — парабола с вершиной в точке $(0, 0)$, ветви направлены вверх. Функция является чётной, убывает на $(-\\infty; 0]$ и возрастает на $[0; +\\infty)$. Множество значений: $y \\ge 0$.',
                        'Функция определена для $x \\ge 0$. График — парабола, ветви направлены вниз. Вершина в точке $(0, 0)$. Функция убывает при $x > 0$ и возрастает при $x < 0$.',
                        'Область определения: все числа. Функция нечётная: $(-x)^2 = -x^2$. График симметричен относительно начала координат. Нуль функции: $x = 0$. Промежутки знакопостоянства: $y > 0$ при $x > 0$, $y < 0$ при $x < 0$.',
                        'Область определения: все действительные числа, кроме нуля. Область значений: $y \\ge 0$. Функция возрастает на всей числовой прямой. График — гипербола, симметричная относительно оси ординат.'
                    ]
                    ep['answer_options_latex'] = ep['answer_options']
                    modified = True

                elif tid == 'G9_TB_24_461.3':
                    ep['correct_answer'] = 'нет'
                    ep['correct_answer_latex'] = 'нет'
                    ep['answer_options'] = ['нет', 'да', 'да, только для первого неравенства', 'да, только для второго неравенства']
                    ep['answer_options_latex'] = ['нет', 'да', 'да, только для первого неравенства', 'да, только для второго неравенства']
                    ep['question_text'] = 'Является ли пара чисел $(-2; -1)$ решением системы неравенств: $\\begin{cases} x^2 - 2y > 7 \\\\ 3x + y > 3 \\end{cases}$?'
                    ep['question_latex'] = 'Является ли пара чисел $(-2; -1)$ решением системы неравенств: $\\begin{cases} x^{2} - 2y > 7 \\\\ 3x + y > 3 \\end{cases}$?'
                    modified = True

        if modified:
            cur.execute('''
                UPDATE diag_reports
                SET report_json = %s
                WHERE session_id = %s;
            ''', (json.dumps(rj, ensure_ascii=False), session_id))
            updated_reports += 1

    print(f"diag_reports: Updated {updated_reports} report snapshot(s).")
    conn.commit()
    conn.close()
    print("Diagnostic DB updates committed successfully.\n")

if __name__ == '__main__':
    update_content_db()
    update_diagnostic_history()
    print("ALL FIXES APPLIED SUCCESSFULLY!")
