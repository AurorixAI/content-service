import psycopg2,re,json,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,distractor_meta from tasks_master where is_active and distractor_meta is not null")
PH=re.compile(r'^\s*Типичная ошибка',re.I)
keys=collections.Counter(); tasks=0; opts=0; other_real=collections.Counter(); fully_empty=0; ex=[]
for i,dm in cur.fetchall():
    hit=False
    for x in dm or []:
        fields={k:str(v) for k,v in x.items() if isinstance(v,str)}
        ph=[k for k,v in fields.items() if PH.match(v)]
        if not ph: continue
        hit=True; opts+=1; keys.update(ph)
        real=[k for k,v in fields.items() if k not in ('value','value_latex','source','error_type') and not PH.match(v) and len(v.strip())>25]
        if real:
            other_real.update(real)
            if len(ex)<6: ex.append((i,{k:fields[k][:120] for k in real}))
        else: fully_empty+=1
    if hit: tasks+=1
print('tasks',tasks,'options',opts); print('placeholder in fields',keys.most_common()); print('options with other real text',sum(1 for _ in [])) 
print('real text fields',other_real.most_common()); print('options with NO real text anywhere',fully_empty)
for e in ex: print(e)
