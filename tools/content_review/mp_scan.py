import re,json,psycopg2
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password')
cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,question_text,correct_answer from tasks_master where is_active")
M=re.compile(r'(?:^|[\s;,.:])([а-яa-e])\)')
M2=re.compile(r'(?:^|[\s;,.:])(\d)\)')
out=[]
n=0
for i,q,k,qt,kt in cur.fetchall():
    q=q or qt or ''; k=k or kt or ''
    qm=set(M.findall(q)); km=set(M.findall(k))
    q2=set(M2.findall(q)); k2=set(M2.findall(k))
    if len(qm)>=2 and len(km)<len(qm) and not (len(km)==0 and ';' in k and k.count(';')+1>=len(qm)):
        out.append((i,'L',sorted(qm),sorted(km)))
    elif len(q2)>=2 and len(k2)<len(q2) and not (len(k2)==0 and (';' in k or ',' in k) and (k.count(';')+1)>=len(q2)):
        out.append((i,'N',sorted(q2),sorted(k2)))
print(len(out))
json.dump(out,open('mp_scan.json','w'),ensure_ascii=False)
from collections import Counter
print(Counter(o[1] for o in out))
for o in out[:60]: print(o)
