import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where is_active")
pat=re.compile(r'[=+\-−<>]\s*\$[^\s$]+\$\s*[+\-=]?[^\s$]*\$|\$[^$]*\$[A-Za-z0-9^_{}\\]+\$[^$\s]')
pat2=re.compile(r'(?<=[=+])\$(?=[A-Za-z0-9\\(])')
n=0
for i,q,k,d in cur.fetchall():
    for lab,s in [('Q',q),('K',k)]+[(f'D{j}',x.get('value_latex') or x.get('value')) for j,x in enumerate(d or [])]:
        s=s or ''
        # odd number of $ signs or pattern
        t=s.replace('$$','')
        if t.count('$')%2==1 or pat2.search(s):
            n+=1; print(i,lab,re.sub(r'\s+',' ',s)[:110]); break
print(n)
