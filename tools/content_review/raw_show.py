import sys,psycopg2
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
lim=int(sys.argv[2]) if len(sys.argv)>2 else 400
for i in sys.argv[1].split('|'):
    cur.execute("select question_latex,correct_answer_latex,distractor_meta from tasks_master where id=%s",(i,))
    r=cur.fetchone()
    if not r: print(i,'NOT FOUND'); continue
    print('##',i); print(' Q:',repr(r[0])[:lim]); print(' K:',repr(r[1])[:lim])
    for n,d in enumerate(r[2] or []): print('  D%d:'%n,repr(d.get('value_latex') or d.get('value'))[:lim],'||',(d.get('explanation') or '')[:90].replace('\n',' '))
