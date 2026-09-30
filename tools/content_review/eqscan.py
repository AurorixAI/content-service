import psycopg2,re,json,sys
from sympy import sympify, nsimplify, N, pi, sqrt, Rational, simplify
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
def brace(s,i):
    d=0
    for j in range(i,len(s)):
        if s[j]=='{': d+=1
        elif s[j]=='}':
            d-=1
            if d==0: return j
    return -1
def conv(s):
    s=re.sub(r'(-?)\s*(\d+)\s*\\d?frac\s*\{(\d+)\}\s*\{(\d+)\}',lambda m:('-' if m.group(1) else '')+'('+m.group(2)+'+'+m.group(3)+'/'+m.group(4)+')' if not m.group(1) else '-('+m.group(2)+'+'+m.group(3)+'/'+m.group(4)+')',s)
    s=s.replace('\\dfrac','\\frac').replace('\\tfrac','\\frac').replace('\\left','').replace('\\right','').replace('\\,','').replace('\\ ','').replace('\\!','')
    s=s.replace('{,}','.').replace('−','-').replace('\\cdot','*').replace('\\times','*').replace('\\pi','pi').replace('°','')
    s=re.sub(r'\\circ','',s); s=s.replace('^{}','').replace('\\%','').replace('%','')
    # frac and sqrt recursive
    for _ in range(20):
        m=re.search(r'\\frac\s*\{',s)
        if not m: break
        i=m.end()-1; j=brace(s,i); 
        if j<0: return None
        k=j+1
        if k>=len(s) or s[k]!='{': return None
        l=brace(s,k)
        s=s[:m.start()]+'(('+s[i+1:j]+')/('+s[k+1:l]+'))'+s[l+1:]
    for _ in range(20):
        m=re.search(r'\\sqrt\s*\{',s)
        if not m: break
        i=m.end()-1; j=brace(s,i)
        s=s[:m.start()]+'sqrt('+s[i+1:j]+')'+s[j+1:]
    s=s.replace('{','(').replace('}',')').replace('^','**')
    s=re.sub(r'(\d)\s*\(',r'\1*(',s); s=re.sub(r'\)\s*(\d|\()',r')*\1',s); s=re.sub(r'(\d)\s*(pi|sqrt)',r'\1*\2',s)
    s=re.sub(r'(\d)\s+(\d)',r'\1\2',s)
    return s
def atoms(v):
    v=(v or '').replace('$','').strip().rstrip('.')
    if re.search(r'[a-zA-Zа-яА-Я]',re.sub(r'\\(dfrac|frac|sqrt|pi|cdot|left|right|circ|times|infty|cup|in|le|ge|leq|geq|ne|neq|mathbb|varnothing|ldots)|\bpi\b','',re.sub(r'\b[xyabtnuvz]_?\{?\d?\}?\s*=','',v))): 
        return None
    parts=[p for p in re.split(r'[;,](?!\d)|\s+или\s+|\s+и\s+',v.replace('\\ ',' ')) if p.strip()]
    # decimal comma safety: '{,}' converted later
    out=[]
    for p in parts:
        p=p.strip().strip('()')
        mv=re.match(r'\s*([xyabtnuvz](?:_?\{?\d\}?)?)\s*=\s*(.*)',p)
        var=None
        if mv: var,p=mv.group(1),mv.group(2)
        cs=conv(p)
        if cs is None: return None
        try:
            val=sympify(cs)
            out.append((var,round(float(N(val)),9)))
        except Exception: return None
    return out if out else None
cur.execute("select id,correct_answer_latex,distractor_meta from tasks_master where is_active and distractor_meta is not null")
hits=[]
for i,k,dm in cur.fetchall():
    ka=atoms(k)
    if not ka: continue
    for idx,x in enumerate(dm or []):
        v=x.get('value_latex') or x.get('value')
        da=atoms(v)
        if da and da==ka:
            hits.append((i,idx,k,v)); break
print(len(hits))
json.dump(hits,open('eq_hits.json','w'),ensure_ascii=False)
for h in hits[:80]: print(h)
