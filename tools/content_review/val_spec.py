import json,sys,psycopg2
n=sys.argv[1]
J=json.load(open(f'/audit/restore_J_{n}.json'))
c=psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
kx={};bad=0
for t,e in J.items():
    c.execute("select question_latex,correct_answer_latex,distractor_meta from tasks_master where id=%s",(t,)); q,k,dm=c.fetchone()
    f=e['fields']; q=f.get('question_latex',q); k=f.get('correct_answer_latex',k); dm=f.get('distractor_meta',dm) or []
    vals=[(d.get('value_latex') or d['value']) for d in dm]
    ex=[d.get('explanation_latex') or d.get('explanation') or '' for d in dm]
    pr=[]
    if len(dm)<2 and not any(x in q.lower() for x in ['да','нет']): pr.append('few')
    if k in vals: pr.append('d==key')
    if len(set(vals))!=len(vals): pr.append('dupvals')
    for s in [q or '',k or '']+vals+ex:
        if s.count('$')%2: pr.append('odd$:'+s[:70])
    if pr: bad+=1; print(t,pr)
    kx[t]=[s for s in [q,k]+vals+ex if s]
json.dump(kx,open(f'/audit/kx_{n}.json','w'),ensure_ascii=False); print('problems',bad,'of',len(J))
