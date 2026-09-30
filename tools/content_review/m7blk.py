import psycopg2, sys
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, is_active, left(regexp_replace(question_latex,'\s+',' ','g'),90) FROM tasks_master WHERE id ~ %s ORDER BY id", (sys.argv[1],))
for r in c.fetchall(): print(r)
