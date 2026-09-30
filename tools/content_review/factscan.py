import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex ~* 'на множител' order by id")
rows=cur.fetchall(); print(len(rows))
bad=[]
for i,q,k in rows:
    k=k or ''
    if not re.search(r'\(|\\cdot|\\left|\^\{?\d\}?\s*\w|\bпро|\\times|\\text',k) or not re.search(r'[\(\)]|\\cdot|\\times|\\text|[a-zA-Z0-9\}]\s*[a-zA-Z\\]', k):
        bad.append((i,re.sub(r'\s+',' ',q)[:90],k[:80]))
for b in bad: print(b)
print(len(bad))
