import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute(r"""SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active AND (question_latex ~ 'le ftrightarrow|leftrightarrow|↔|микрокалькулятор')""")
for r in c.fetchall(): print(r[0], "\n  Q:", r[1][:260], "\n  K:", (r[2] or "")[:200])
