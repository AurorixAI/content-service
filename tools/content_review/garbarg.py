import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex like '%pi%'")
for i,q,k in cur.fetchall():
    if re.search(r'\\dfrac\{\\pi\}\{\d+\s*[-+]\s*\d*[a-z]\}',q or ''): print(i,'|',re.sub(r'\s+',' ',q)[:120],'| K',(k or '')[:80])
