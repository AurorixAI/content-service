import psycopg2,json,re,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
J=json.load(open('restore_J_ctrl17.json'))
k=collections.Counter()
for t in J:
    cur.execute("select correct_answer,jsonb_array_length(distractor_meta),distractor_meta->0->>'value' from tasks_master where id=%s",(t,)); ca,n,v=cur.fetchone()
    if n<2: k[(str(ca).strip().lower()[:12], str(v).strip().lower()[:12])]+=1
print(k.most_common())
