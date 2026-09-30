import psycopg2,json,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
bad=json.load(open('reatt_bad.json'))
shown={'splitdec':0,'latex_outside_math':0,'garble':0,'odd$':0}
for tid,p in bad.items():
    cur.execute("select question_text,correct_answer,answer_options,distractor_meta from tasks_master where id=%s",(tid,))
    qt,ca,ao,dm=cur.fetchone()
    fields={'q':qt,'a':ca}
    for i,x in enumerate(ao or []): fields[f'opt{i}']=x
    for i,x in enumerate(dm or []): fields[f'dv{i}']=x.get('value'); fields[f'de{i}']=x.get('explanation')
    for pr in p:
        name,kind=pr.split(':')
        if shown[kind]<6 and name in fields:
            shown[kind]+=1; print(tid,pr,'|',str(fields[name])[:200].replace('\n',' '))
