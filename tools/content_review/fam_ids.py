import psycopg2
c=psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("select id,is_active,left(question_latex,90),left(correct_answer_latex,50) from tasks_master where id ~ '^G5_TB_31_559\\.' or id ~ '^G5_TB_41_702\\.' order by id")
for r in c.fetchall(): print(r)
