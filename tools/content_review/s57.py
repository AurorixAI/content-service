import psycopg2
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where id like 'G5_TB_15_258%' or question_latex like '%числом%(66)%'")
for r in cur.fetchall(): print(r)
