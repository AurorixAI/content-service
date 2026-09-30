import psycopg2,re,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
for t in json.load(open('sysbare_ids.json')):
    cur.execute("select regexp_replace(question_latex,'\\s+',' ','g'),correct_answer_latex,distractor_meta from tasks_master where id=%s",(t,)); q,k,dm=cur.fetchone()
    print(t,'|',q[:230],'| K:',k,'| D:',[str(x.get('value_latex') or x.get('value'))[:22] for x in dm or []])
