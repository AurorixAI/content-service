import psycopg2,re,collections,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,distractor_meta from tasks_master where is_active and distractor_meta is not null")
PH=re.compile(r'^\s*Типичная ошибка',re.I)
texts=collections.Counter(); generic_tasks=set(); generic_opts=0; real_opts=0; gen=[]
for i,dm in cur.fetchall():
    for idx,x in enumerate(dm or []):
        s=str(x.get('error_logic') or x.get('explanation') or '').strip()
        if not PH.match(s): continue
        # generic = no digits/$/specific words and short
        if len(s)<90 and '$' not in s and not re.search(r'\d|:',s):
            texts[s]+=1; generic_tasks.add(i); generic_opts+=1; gen.append((i,idx))
        else: real_opts+=1
print('generic options',generic_opts,'tasks',len(generic_tasks),'| starts with phrase but specific',real_opts)
for t,n in texts.most_common(15): print(n,'|',t)
json.dump(gen,open('generic_ph.json','w'))
# total options & how many generic overall incl other phrasings
cur.execute("select count(*), sum(jsonb_array_length(distractor_meta)) from tasks_master where is_active and distractor_meta is not null and jsonb_typeof(distractor_meta)='array'")
print(cur.fetchone())
