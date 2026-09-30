import re,json,psycopg2
IDS="G7_TB_25_593.1 G7_TB_1_6.1 G7_TB_2_17.1 G7_TB_20_452.1 G7_TB_20_462.1 G7_TB_21_471.1 G7_TB_2_24.1 G7_TB_34_877.1 G7_TB_5_91.1 G7_TB_35_912.1 G7_TB_2_22.1 G7_TB_34_876.1 G7_TB_18_397.1 G7_TB_18_399.1 G7_TB_18_399.3 G7_TB_18_397.2 G7_TB_18_396.1 G7_TB_18_396.2".split()
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
out={}
for t in IDS:
    cur.execute("select question_latex,correct_answer_latex,distractor_meta from tasks_master where id=%s",(t,))
    q,k,dm=cur.fetchone()
    m=re.match(r'^(.*?:)\s*\n?(?:[аб]\)|)\s*(.*?)\s*[;.]?\s*\n(?:[бвг])\)',q,re.S)
    if not m: print("NOMATCH",t,repr(q)); continue
    hdr,item=m.group(1),m.group(2)
    if item.startswith('а) '): item=item[3:]
    nq=hdr+" "+item
    ks=re.sub(r'^а\)\s*','',k)
    ds=dm['distractors'] if isinstance(dm,dict) else dm
    dval={i:re.sub(r'^[а-г]\)\s*','',d.get('value_latex') or d['value']) for i,d in enumerate(ds)}
    dval={i:v for i,v in dval.items() if v!=(ds[i].get('value_latex') or ds[i]['value'])}
    mention=[(i,d.get('explanation') or d.get('why') or d.get('text')) for i,d in enumerate(ds)]
    out[t]=dict(q=nq,k=ks,dval=dval)
    print(t,'|',nq,'|K',ks,'|dval',dval)
    for i,e in mention:
        if e and re.search(r'пункт|[бвг]\)|в\) или|пункта',e): print('   !!EXPL',i,e)
json.dump(out,open('narrow_gen.json','w'),ensure_ascii=False,indent=1)
