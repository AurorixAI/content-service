import psycopg2,json,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
A=json.load(open('meta_hits.json')); B=json.load(open('meta3_hits.json'))
bset={(h[0],h[1]) for h in B}
rest=[h for h in A if (h[0],h[1]) not in bset]
print(len(rest))
for i,idx,m,e in rest:
    cur.execute("select regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex,distractor_meta from tasks_master where id=%s",(i,)); q,k,dm=cur.fetchone()
    x=dm[idx]
    print(f"## {i} D{idx} [{m}] | Q: {q[:150]} | K: {(k or '')[:60]} | D: {str(x.get('value_latex') or x.get('value'))[:60]}\n    E: {e[:230]}")
