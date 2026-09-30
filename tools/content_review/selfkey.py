import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and correct_answer_latex is not null")
def norm(s): return re.sub(r'[\s$]|\\,|\\!|\\left|\\right|\{,\}|\\dfrac|\\frac|\\cdot','',s or '').replace('−','-')
n=0
for i,q,k in cur.fetchall():
    kn=norm(k)
    if len(kn)<5: continue
    qi=re.findall(r'\$([^$]+)\$',q or '')
    qn=[norm(x) for x in qi]
    if re.search(r'Упрост|Разложите|Сократите|Преобразуйте|Вынесите|Представьте|Освободитесь|Выполните|Раскройте|Приведите',q or '') and any(kn==x for x in qn):
        n+=1; print(i,'|',re.sub(r'\s+',' ',q)[:110],'| K',k[:60])
print(n)
