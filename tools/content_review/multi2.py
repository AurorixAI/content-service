import psycopg2,re,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active")
out=[]
for i,q,k in cur.fetchall():
    q1=re.sub(r'\s+',' ',q or ''); k=k or ''
    labs=re.findall(r'(?:^|[\s;:.])([а-е])\)\s',q1)
    nums=re.findall(r'(?:^|\s)([1-6])\)\s',q1)
    n=max(len(set(labs)),len(set(nums)))
    if n>=2:
        kl=len(re.findall(r'(?:^|[\s;,])[а-е1-6]\)',k))
        ks=len([p for p in re.split(r'[;]',k) if p.strip()])
        if kl<2 and ks<n:
            out.append((i,n,k[:60],q1[:80]))
print(len(out))
import collections
print(collections.Counter(o[0].split('_')[0]+'_'+o[0].split('_')[1] for o in out).most_common(10))
json.dump(out,open('multi2.json','w'),ensure_ascii=False)
for o in out[:40]: print(o)
