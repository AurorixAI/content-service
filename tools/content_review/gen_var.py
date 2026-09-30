import psycopg2,re,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute(r"select id,question_latex,correct_answer_latex,distractor_meta from tasks_master where is_active and correct_answer_latex ~ '^\$?\s*x(_\{?[0-9]\}?)?\s*='")
def qvars(q):
    t=' '.join(re.findall(r'\$([^$]+)\$',q))
    t=re.sub(r'\\(sin|cos|tg|ctg|tan|cot|log|lg|ln|sqrt|frac|dfrac|cdot|left|right|operatorname|text|mathbb|in|pi|arcsin|arccos|arctg|arcctg|lim|infty|to|le|ge|leq|geq|neq|cup|cap|pm|approx|circ|cases|begin|end|not|varnothing)\b','',t)
    return set(re.findall(r'(?<![a-zA-Z\\])([a-zA-Z])(?![a-zA-Z])',t))
items=[]
for i,q,k,d in cur.fetchall():
    if not re.search(r'Решите|Найдите корни|корн',q or ''): continue
    qv=qvars(q or '')
    if 'x' in qv or len(qv)!=1: continue
    v=list(qv)[0]
    if v in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ': continue
    newk=re.sub(r'(?<![a-zA-Z\\])x(?=(_\{?\d\}?)?\s*=)',v,k)
    items.append((i,v,k,newk))
for it in items: print(it)
json.dump(items,open('varfix.json','w'),ensure_ascii=False)
print(len(items))
