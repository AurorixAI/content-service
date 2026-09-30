import re,psycopg2,json,collections
c=psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("select id,coalesce(question_latex,question_text),coalesce(correct_answer_latex,correct_answer),answer_options from tasks_master where is_active")
out=[];cnt=collections.Counter()
for i,q,k,ao in c.fetchall():
    q=q or ''; k=k or ''
    labs=re.findall(r'(?:^|[\s;(:.,])([абвгдеж])\)',q)
    if len(set(labs))<2: continue
    if re.search(r'[абвгдеж]\)',k): continue
    if re.search(r'(?:^|[;,\s])(1|2)\)',k): continue
    if k.count(';')>=len(set(labs))-1 and len(set(labs))>1 and ';' in k: continue
    out.append((i,q[:160].replace('\n',' '),k[:70]))
    cnt[i.split('_')[0]+'_'+i.split('_')[1] if i.startswith('G') else i[:6]]+=1
json.dump(out,open('multi_scan.json','w'),ensure_ascii=False,indent=0)
print(len(out)); print(cnt.most_common(20))
for o in out[:40]: print(o)
