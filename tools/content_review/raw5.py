import psycopg2,sys
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
for t in sys.argv[1].split('|'):
    cur.execute("select question_text,question_latex,correct_answer,correct_answer_latex,distractor_meta from tasks_master where id=%s",(t,))
    qt,ql,ca,cal,dm=cur.fetchone(); print('##',t,'\n QT:',qt,'\n QL:',ql,'\n CA:',ca,'\n CAL:',cal)
    for i,x in enumerate(dm): print(f' D{i} v:',x.get('value'),'| vl:',x.get('value_latex'))
