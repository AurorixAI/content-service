import psycopg2,re,json,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where is_active")
R=cur.fetchall()
# 1 placeholder explanations
ph=[r[0] for r in R if any(re.match(r'^\s*Типичная ошибка',str(x.get('explanation') or x.get('error_logic') or '')) for x in (r[3] or []))]
print('placeholder expl tasks',len(ph)); json.dump(ph,open('ph_ids.json','w'))
print(collections.Counter(i.rsplit('_',1)[0][:14] for i in ph).most_common(8))
# 2 sibling permutation: key numbers == another sibling's question numbers
num=lambda s: tuple(sorted(re.findall(r'\d+(?:\{,\}\d+|[.,]\d+)?',re.sub(r'\\[a-zA-Z]+','',s or ''))))
fam=collections.defaultdict(list)
for i,q,k,d in R:
    m=re.match(r'^(.*)[._]\d+(?:\.\d+)?$',i)
    if m: fam[m.group(1)].append((i,q,k))
hits=[]
for f,lst in fam.items():
    if len(lst)<2 or len(lst)>60: continue
    qn={i:num(q) for i,q,k in lst}
    for i,q,k in lst:
        kn=num(k)
        if len(kn)<2 or kn==qn[i]: continue
        for j,qj in qn.items():
            if j!=i and qj==kn and len(qj)>=2: hits.append((i,j)); break
print('perm hits',len(hits)); print(hits[:40])
json.dump(hits,open('perm_hits.json','w'))
