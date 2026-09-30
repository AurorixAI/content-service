import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where is_active")
pat=re.compile(r'опечатк|расчет велся|расчёт велся|\(но |в тексте опечатка|no solutions|solution|\bthe\b|\bis\b',re.I)
for i,q,k,dm in cur.fetchall():
    if pat.search(q or '') : print('Q',i,(q or '')[:160].replace('\n',' '))
    if pat.search(k or ''): print('K',i,(k or '')[:120])
    for idx,x in enumerate(dm or []):
        v=str(x.get('value_latex') or x.get('value') or '')
        if pat.search(v): print('D',i,idx,v[:140])
