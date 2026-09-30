import psycopg2,json,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta::text from tasks_master where is_active")
pat=re.compile(r'\$\d+\$[.,]\$\d')
n=0;ids=[]
for i,q,k,d in cur.fetchall():
    txt=(q or '')+(k or '')+(d or '')
    if pat.search(txt): ids.append(i)
print(len(ids)); json.dump(ids,open('dot_ids.json','w')); print(ids[:20])
