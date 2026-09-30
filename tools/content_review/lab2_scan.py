import re,psycopg2
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,coalesce(question_latex,question_text),coalesce(correct_answer_latex,correct_answer) from tasks_master where is_active")
n=0
for i,q,k in cur.fetchall():
    k=(k or '').strip(); q=q or ''
    m=re.match(r'([абвгдежзиклмn])\)\s',k)
    if m and not re.search(r'(?:^|[\s;,.:(])'+m.group(1)+r'\)',q):
        n+=1; print(i,'|K:',k[:80].replace('\n',' '),'|Q:',q[:110].replace('\n',' '))
print(n)
