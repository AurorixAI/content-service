import psycopg2,json,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
for i,h,n in json.load(open('nonans.json')):
    cur.execute("select regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex,distractor_meta from tasks_master where id=%s",(i,)); q,k,dm=cur.fetchone()
    print(f"{i} [{len(h)}/{n}] Q: {q[:110]} | K: {(k or '')[:40]} | D: {[str(x.get('value_latex') or x.get('value'))[:22] for x in dm]}")
