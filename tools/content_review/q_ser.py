import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute(r"SELECT id, question_latex, correct_answer, answer_options FROM tasks_master WHERE is_active AND (id LIKE 'G5_TB_38_1483.%%' OR id LIKE 'G5_TB_38_1511.%%') ORDER BY id")
for r in c.fetchall(): print(r[0], '|', r[1][-45:], '| K:', r[2], '| AO:', r[3])
