import re,json,psycopg2
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,coalesce(question_latex,question_text),coalesce(correct_answer_latex,correct_answer),distractor_meta from tasks_master where is_active")
L=re.compile(r'(?:^|[\s;,.])([абвгдежзabcd])\)')
n=0
for i,q,k,dm in cur.fetchall():
    k=k or ''
    ks=L.findall(k)
    if not ks: continue
    first=ks[0]
    # key labeled: first label should be 'а' (or 'a'); flag if key starts w/o label but has later labels
    if not re.match(r'\s*[\$\(]*\s*[аa]\)',k) and 'а' not in ks and 'a' not in ks and len(ks)>=1 and not k.strip().startswith(('а)','a)')):
        n+=1; print(i,'|K:',k[:120].replace('\n',' '),'|nd',len(dm or []))
print(n)
