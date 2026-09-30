import psycopg2
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where id like 'G5_TB_13_258а.%' order by id")
for i,q,k,d in cur.fetchall(): print(i,'|',q[-60:],'|',k,'|',[x.get('value') for x in d])
