import psycopg2
import json

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

# Task 1: G11_TB_§5_5_54
qt_1 = r'Докажите, что функция $f(x) = \frac{1}{x}$ убывает на каждом из промежутков $(-\infty; 0)$ и $(0; +\infty)$.'
ql_1 = r'Докажите, что функция $f(x) = \dfrac{1}{x}$ убывает на каждом из промежутков $(-\infty; 0)$ и $(0; +\infty)$.'
ca_1 = r"$f'(x) = -\frac{1}{x^2} < 0$ при всех $x \neq 0$, следовательно, функция убывает на каждом из промежутков $(-\infty; 0)$ и $(0; +\infty)$."
cal_1 = r"$f'(x) = -\dfrac{1}{x^2} < 0$ при всех $x \neq 0$, следовательно, функция убывает на каждом из промежутков $(-\infty; 0)$ и $(0; +\infty)$."

cur.execute('''
    UPDATE tasks_master
    SET question_text = %s,
        question_latex = %s,
        correct_answer = %s,
        correct_answer_latex = %s,
        latex_status = 'verified'
    WHERE id = 'G11_TB_§5_5_54'
''', (qt_1, ql_1, ca_1, cal_1))

# Task 2: ds_llm_fa538615ad37
qt_2 = r'Решите систему уравнений: $\begin{cases} \sqrt{x^{2}-y^{2}} = 4 \\ x + y = 8 \end{cases}$'
ql_2 = r'Решите систему уравнений: $\begin{cases} \sqrt{x^{2}-y^{2}} = 4 \\ x + y = 8 \end{cases}$'

cur.execute('''
    UPDATE tasks_master
    SET question_text = %s,
        question_latex = %s,
        latex_status = 'verified'
    WHERE id = 'ds_llm_fa538615ad37'
''', (qt_2, ql_2))

# Task 3: G8_TB_28_671.2
qt_3 = r'Является ли пара чисел $(-1; 3)$ решением уравнения $xy + y = 6$?'
ql_3 = r'Является ли пара чисел $(-1; 3)$ решением уравнения $xy + y = 6$?'

cur.execute('''
    UPDATE tasks_master
    SET question_text = %s,
        question_latex = %s,
        latex_status = 'verified'
    WHERE id = 'G8_TB_28_671.2'
''', (qt_3, ql_3))

# Task 4: G7_ALG_28_1
qt_4 = "Найдите уравнение, корнем которого является число $-3$:\n1) $-3x = 12$\n2) $2x - 7 = -13$\n3) $\\frac{1}{3x} = -1$\n4) $5(x - 2) + 1 = 4x$"
ql_4 = "Найдите уравнение, корнем которого является число $-3$:\n1) $-3x = 12$\n2) $2x - 7 = -13$\n3) $\\dfrac{1}{3x} = -1$\n4) $5(x - 2) + 1 = 4x$"

cur.execute('''
    UPDATE tasks_master
    SET question_text = %s,
        question_latex = %s,
        latex_status = 'verified'
    WHERE id = 'G7_ALG_28_1'
''', (qt_4, ql_4))

conn.commit()
print('Successfully saved perfectly clean 4 tasks in tasks_master!')
