import psycopg2,sys
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
for t in sys.argv[1].split('|'):
    cur.execute("select question_latex,correct_answer_latex,is_active from tasks_master where id=%s",(t,)); print(t,cur.fetchall())
