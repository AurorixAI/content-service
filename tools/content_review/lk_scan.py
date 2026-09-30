import re,psycopg2
L='абвгдежзиклмноп'
c=psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("select id,coalesce(question_latex,question_text),coalesce(correct_answer_latex,correct_answer) from tasks_master where is_active")
n=0
for i,q,k in c.fetchall():
    q=q or '';k=(k or '').strip()
    ks=re.findall(r'(?:^|[\s,;(и])([абвгдежзиклмноп])(?=[\s,;).]|$)',k) if re.fullmatch(r'[а-яa-z0-9,;.\s\)и$]*',k) and len(k)<40 else []
    if not ks: continue
    qs=re.findall(r'(?:^|[\s;(:.,])([абвгдежзиклмноп])\)',q)
    if not qs: continue
    mx=max(L.index(x) for x in qs)
    bad=[x for x in ks if L.index(x)>mx and len(k)<40 and re.fullmatch(r'[абвгдежзиклмноп](\s*,\s*[абвгдежзиклмноп])*',k)]
    if bad: n+=1; print(i,'|K:',k,'|Q labels:',''.join(sorted(set(qs))),'|',q[:90].replace('\n',' '))
print(n)
