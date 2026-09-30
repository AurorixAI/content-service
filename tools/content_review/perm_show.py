import psycopg2,json,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
H=json.load(open('perm_hits.json'))
for i,j in H:
    cur.execute("select regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex from tasks_master where id=%s",(i,)); q,k=cur.fetchone()
    print(f"{i}~{j} | Q: {q[-110:]} | K: {(k or '')[:70]}")
