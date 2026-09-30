import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where is_active and (question_latex like '%right)^{2}%' or correct_answer_latex like '%right)^{2}%')")
pat=re.compile(r'\\left\(\s*\\dfrac\{-?[^{}]+\}\{[^{}]+\}\s*\\right\)\^\{2\}')
for i,q,k,d in cur.fetchall():
    if pat.search(k or '') or pat.search(q or ''):
        print(i,'|',re.sub(r'\s+',' ',q)[:90],'| K',(k or '')[:80])
