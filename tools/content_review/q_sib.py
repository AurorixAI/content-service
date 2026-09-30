import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, is_active, left(question_latex,120), correct_answer FROM tasks_master WHERE id LIKE 'G10_TB_1_7_3_%' OR id LIKE 'G10_TB_3_7_3_%' ORDER BY id")
for r in c.fetchall(): print(r)
