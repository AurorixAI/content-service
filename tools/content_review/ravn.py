import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and (question_latex ~* 'равносильн') and id not like 'G10\_TB\_§4\_4\_1\_%' order by id")
for i,q,k in cur.fetchall(): print(i,'|',re.sub(r'\s+',' ',q)[:170],'| K',(k or '')[:70])
