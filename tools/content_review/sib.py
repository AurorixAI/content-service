import psycopg2,sys
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
for p in sys.argv[1:]:
    cur.execute("select id,left(regexp_replace(question_latex,'\\s+',' ','g'),150),left(correct_answer_latex,80),is_active from tasks_master where id like %s order by id",(p,))
    for r in cur.fetchall(): print(r)
