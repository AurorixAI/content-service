import psycopg2,re
from math import gcd
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and correct_answer_latex is not null")
n=0
for i,q,k in cur.fetchall():
    kk=(k or '').strip()
    m=re.fullmatch(r'\$\s*(-?)\s*\\d?frac\{\s*(-?\d+)\s*\}\{\s*(\d+)\s*\}\s*\$\.?',kk)
    if not m: continue
    a,b=abs(int(m.group(2))),int(m.group(3))
    if b>1 and a>0 and gcd(a,b)>1 and not re.search(r'сократ|привед|знаменател|общ|дол|част|верн|прав',q or '',re.I):
        n+=1; print(i,'|',re.sub(r'\s+',' ',q)[:100],'| K',kk)
print(n)
