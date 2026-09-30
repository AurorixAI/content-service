import psycopg2,re,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,distractor_meta from tasks_master where is_active and distractor_meta is not null")
PH=re.compile(r'^\s*Типичная ошибка',re.I)
cat=collections.Counter(); shown=collections.Counter(); samples=collections.defaultdict(list)
for i,dm in cur.fetchall():
    for x in dm or []:
        e=str(x.get('explanation') or '')
        if not PH.match(e): continue
        el=x.get('error_logic'); ell=x.get('error_logic_latex')
        # what diagnostics report shows: error_logic or explanation
        s=(el or e); s=str(s).strip()
        if PH.match(s): k='placeholder'
        elif len(s)<=25: k='short:'+s
        else: k='real'
        cat[k if not k.startswith('short') else 'short']+=1
        if k.startswith('short') and len(samples['short'])<15: samples['short'].append((i,s))
        if k=='placeholder' and len(samples['ph'])<5: samples['ph'].append((i,e))
print(cat)
for k,v in samples.items(): print(k,v)
