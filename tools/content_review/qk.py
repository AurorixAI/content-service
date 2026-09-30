import psycopg2,sys,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
for t in sys.argv[1].split('|'):
    cur.execute("select regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex from tasks_master where id=%s",(t,)); q,k=cur.fetchone()
    print('##',t,'\n Q:',q[:700],'\n K:',k[:200])
