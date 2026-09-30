import psycopg2,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
for i,idx,k,v in json.load(open('eq_hits.json')):
    if i.startswith('G11_TB_?_36'): continue
    cur.execute("select regexp_replace(question_latex,'\\s+',' ','g'),distractor_meta from tasks_master where id=%s",(i,)); q,dm=cur.fetchone()
    e=dm[idx].get('explanation') or ''
    print(f"{i} D{idx}\n  Q: {q[:230]}\n  E: {e[:230]}")
