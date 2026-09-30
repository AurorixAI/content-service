import psycopg2,json,re,sys
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
H=json.load(open('meta3_hits.json'))
seen=set()
for i,idx,m,e in H:
    if re.search(r'опечатк|в базе данных|из базы',e,re.I): seen.add(i)
ids=[]
for i,idx,m,e in H:
    if i not in seen and i not in ids: ids.append(i)
a,b=int(sys.argv[1]),int(sys.argv[2])
print(len(ids))
for i in ids[a:b]:
    cur.execute("select regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex,distractor_meta from tasks_master where id=%s",(i,)); q,k,dm=cur.fetchone()
    print(f"## {i} | Q: {q[:200]} | K: {(k or '')[:70]}")
    for h in H:
        if h[0]==i:
            x=dm[h[1]]; print(f"   D{h[1]}: {str(x.get('value_latex') or x.get('value'))[:50]} || {h[3][:190]}")
