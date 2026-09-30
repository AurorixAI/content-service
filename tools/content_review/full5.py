import psycopg2,sys,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
for t in sys.argv[1].split('|'):
    cur.execute("select question_latex,correct_answer_latex,distractor_meta from tasks_master where id=%s",(t,)); q,k,d=cur.fetchone()
    print("=====",t,"\nQ:",q,"\nK:",k)
    for i,x in enumerate(d or []): print(f" D{i}:",x.get('value_latex') or x.get('value'),"||",x.get('explanation') or x.get('why') or {kk:v for kk,v in x.items() if kk not in('value','value_latex')})
