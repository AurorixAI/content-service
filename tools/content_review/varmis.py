import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where is_active and correct_answer_latex ~ '^\\$?\\s*[a-zA-Z](_\\{?[0-9]\\}?)?\\s*=' ")
n=0;out=[]
def qvars(q):
    t=' '.join(re.findall(r'\$([^$]+)\$',q))
    t=re.sub(r'\\(sin|cos|tg|ctg|tan|cot|log|lg|ln|sqrt|frac|dfrac|cdot|left|right|operatorname|text|mathbb|in|pi|arcsin|arccos|arctg|arcctg|lim|infty|to|le|ge|leq|geq|neq|cup|cap|pm|approx|circ|cases|begin|end|not|varnothing)\b','',t)
    return set(re.findall(r'(?<![a-zA-Z\\])([a-zA-Z])(?![a-zA-Z])',t))
for i,q,k,d in cur.fetchall():
    kv=re.match(r'^\$?\s*([a-zA-Z])',k.strip()).group(1)
    qv=qvars(q or '')
    if not qv: continue
    if kv not in qv and not re.search(r'график|функци|y\s*=|Постройте',q or ''):
        # distractors' variable
        dv=[re.match(r'^\$?\s*([a-zA-Z])',str(x.get('value_latex') or x.get('value')).strip()) for x in d or []]
        dv=[m.group(1) for m in dv if m]
        out.append((i,kv,sorted(qv)[:6],dv[:3],re.sub(r'\s+',' ',q)[:70]))
print(len(out))
for o in out: print(o)
