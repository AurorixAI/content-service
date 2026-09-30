import psycopg2,json,re,collections
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
ids=json.load(open('reatt_ids.json'))
def outside(s):
    s=re.sub(r'\$\$.*?\$\$','',str(s or ''),flags=re.S); return re.sub(r'\$.*?\$','',s,flags=re.S)
def probs(name,s):
    s=str(s or ''); out=[]
    if not s: return out
    t=s.replace('\\$','')
    if t.count('$')%2: out.append(name+':odd$')
    if re.search(r'\$\d+\$[.,]\$\d',s): out.append(name+':splitdec')
    o=outside(s)
    if re.search(r'\\[a-zA-Z]{2,}|[\^_]\{|\{,\}',o): out.append(name+':latex_outside_math')
    if re.search(r'\\\\dfrac|\\\\frac|\bast\b',s): out.append(name+':garble')
    return out
res=collections.Counter(); bad={}
for tid in ids:
    cur.execute("select question_text,correct_answer,answer_options,distractor_meta from tasks_master where id=%s",(tid,))
    qt,ca,ao,dm=cur.fetchone(); p=probs('q',qt)+probs('a',ca)
    for i,x in enumerate(ao or []): p+=probs(f'opt{i}',x)
    for i,x in enumerate(dm or []):
        p+=probs(f'dv{i}',x.get('value')); p+=probs(f'de{i}',x.get('explanation'))
    if p: bad[tid]=p; res.update(set(p))
print(len(bad)); print(res.most_common(20))
json.dump(bad,open('reatt_bad.json','w'),ensure_ascii=False)
for t,p in list(bad.items())[:15]: print(t,p)
