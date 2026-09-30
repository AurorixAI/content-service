import sys, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT correct_answer_latex FROM tasks_master WHERE id=%s", (sys.argv[1],))
print(c.fetchone()[0], end='')
