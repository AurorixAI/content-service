import psycopg2,sys
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
for p in sys.argv[1:]:
    cur.execute("select id,question_text,question_latex,correct_answer_latex,distractor_meta,is_active from tasks_master where id like %s order by id",(p,))
    for i,qt,ql,k,dm,a in cur.fetchall():
        print(i,a,'\n  QT:',repr(qt),'\n  QL:',repr(ql),'\n  K:',k,'\n  D:',[str(x.get('value_latex') or x.get('value'))[:60] for x in dm or []])
