import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute(r"select id,question_latex,correct_answer_latex from tasks_master where is_active and id like 'G5\_%' and (correct_answer_latex ~ '\\pm|-' )")
for i,q,k in cur.fetchall(): print(i,'|',re.sub(r'\s+',' ',q)[:90],'| K',k[:50])
