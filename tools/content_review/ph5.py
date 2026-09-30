import psycopg2,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,distractor_meta from tasks_master where is_active and distractor_meta is not null")
cnt=collections.Counter(); tasks=collections.defaultdict(set); empty=0; et=set()
for i,dm in cur.fetchall():
    for x in dm or []:
        s=str(x.get('error_logic') or x.get('explanation') or '').strip()
        if not s: empty+=1; et.add(i); continue
        cnt[s]+=1; tasks[s].add(i)
rep=[(n,s) for s,n in cnt.items() if n>=15]
rep.sort(reverse=True)
tot=0
for n,s in rep[:30]: print(n,len(tasks[s]),'|',s[:110]); tot+=n
print('repeated>=15 total',sum(n for n,s in rep),'| empty explanations',empty,'tasks',len(et))
