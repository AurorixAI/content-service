import json,psycopg2
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password')
cur=c.cursor()
out=[o for o in json.load(open('mp_scan.json')) if o[1]=='L']
for o in out:
    cur.execute("select coalesce(question_latex,question_text),coalesce(correct_answer_latex,correct_answer) from tasks_master where id=%s",(o[0],))
    q,k=cur.fetchone()
    print(o[0],'|Q:',q.replace('\n',' ')[:170],'|K:',k.replace('\n',' ')[:110])
