import psycopg2,json,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
H=json.load(open('meta3_hits.json'))
ids=[]
for i,idx,m,e in H:
    if re.search(r'опечатк|в базе данных|из базы',e,re.I) and i not in ids: ids.append(i)
print(len(ids))
for i in ids:
    cur.execute("select regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex,distractor_meta from tasks_master where id=%s",(i,)); q,k,dm=cur.fetchone()
    print(f"## {i}\n Q: {q[:260]}\n K: {(k or '')[:110]}")
    for idx,x in enumerate(dm):
        e=str(x.get('explanation') or '')
        if re.search(r'опечатк|в базе данных|из базы',e,re.I): print(f"  D{idx}: {str(x.get('value_latex') or x.get('value'))[:60]} || {e[:150]}")
