import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex like '%dfrac%'")
n=0
for i,q,k in cur.fetchall():
    for m in re.finditer(r'\\(?:sin|cos|tan|tg|ctg|arcsin|arctg|arctan)\s*\\dfrac\{([^{}]+)\}\{([^{}]+)\}',q or ''):
        n+=1; print(i,'|',re.sub(r'\s+',' ',q)[:130],'| K',(k or '')[:40]); break
print(n)
