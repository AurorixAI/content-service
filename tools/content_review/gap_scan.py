import re,psycopg2
L='абвгдежзиклмноп'
c=psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("select id,coalesce(question_latex,question_text),coalesce(correct_answer_latex,correct_answer) from tasks_master where is_active")
n=0
for i,q,k in c.fetchall():
    q=q or ''
    qs=sorted(set(re.findall(r'(?:^|[\s;(:.,])([абвгдежзиклмноп])\)',q)),key=L.index)
    if not qs: continue
    idx=[L.index(x) for x in qs]
    if idx==list(range(min(idx),max(idx)+1)) and min(idx)==0: continue
    if len(qs)<2 and idx[0]==0: continue
    n+=1; print(i,''.join(qs),'|K:',(k or '')[:50].replace('\n',' '),'|',q[:100].replace('\n',' '))
print(n)
