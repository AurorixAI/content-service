import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute(r"select id,question_latex,correct_answer_latex from tasks_master where is_active and (correct_answer_latex ~ '\\d?frac\{[^{}]*\}\{ *-' or correct_answer_latex ~ '\\d?frac\{[0-9]+\}\{[0-9]+\}.*\\d?frac' and false)")
for i,q,k in cur.fetchall(): print(i,'|',re.sub(r'\s+',' ',q)[:100],'| K',k[:70])
