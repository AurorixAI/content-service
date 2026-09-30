import psycopg2,re,json,random,math
from sympy import symbols, sympify, lambdify, sin,cos,tan,cot,log,sqrt,exp,pi,Symbol
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
    s=s.replace('$','').strip().rstrip('.')
    if re.search(r'[=<>≤≥]|\\le|\\ge|\\in|\\cup|\;|;|,|\\text|\\neq|\\Rightarrow|или|при|\\lim|\\int',s): return None
    s=s.replace('\\dfrac','\\frac').replace('\\left','').replace('\\right','').replace('\\cdot','*').replace('\\,','').replace('\\ ','').replace('\\pi','pi')
    s=s.replace('\\operatorname{tg}','\\tg').replace('\\operatorname{ctg}','\\ctg')
    for _ in range(30):
        m=re.search(r'\\frac\s*\{',s)
        if not m: break
        i=m.end()-1;j=brace(s,i)
        if j<0 or j+1>=len(s) or s[j+1]!='{': return None
        l=brace(s,j+1); 
        s=s[:m.start()]+'(('+s[i+1:j]+')/('+s[j+2:l]+'))'+s[l+1:]
    for _ in range(30):
        m=re.search(r'\\sqrt\s*\{',s)
        if not m: break
        i=m.end()-1;j=brace(s,i); s=s[:m.start()]+'sqrt('+s[i+1:j]+')'+s[j+1:]
    for a,b in [('\\sin','sin'),('\\cos','cos'),('\\tg','tan'),('\\ctg','cot'),('\\ln','log'),('\\lg','log')]: s=s.replace(a,b)
    if '\\' in s: return None
    s=re.sub(r'(sin|cos|tan|cot|log10|log)\s*\^\{?(\d+)\}?\s*([a-z0-9(]+)',lambda m:f'({m.group(1)}({m.group(3)}))**{m.group(2)}',s)
    s=re.sub(r'(sin|cos|tan|cot|log10|log)\s+([a-z0-9]+)',r'\1(\2)',s)
    s=s.replace('{','(').replace('}',')').replace('^','**')
    s=re.sub(r'(\d|\))\s*([a-zA-Z(])',r'\1*\2',s); s=re.sub(r'([a-z])\s*\(',lambda m:m.group(0),s)
    s=re.sub(r'\)\s*\(',r')*(',s)
    s=re.sub(r'(?<![a-z])([xyabntkmpqcz])([xyabntkmpqcz])(?![a-z(])',r'\1*\2',s)
    s=re.sub(r'(?<![a-z])([xyabntkmpqcz])([xyabntkmpqcz])(?![a-z(])',r'\1*\2',s)
    s=s.replace('{,}','.')
    return s
def num(expr,syms,vals):
    try:
        f=lambdify(syms,expr,'math'); v=f(*vals)
        return float(v) if isinstance(v,(int,float)) and math.isfinite(v) else None
    except Exception: return None
def parse(s):
    cs=conv(s)
    if not cs: return None
    try:
        e=sympify(cs,locals={'pi':pi})
        return e if hasattr(e,'free_symbols') else None
    except Exception: return None
cur.execute("select id,correct_answer_latex,distractor_meta from tasks_master where is_active and distractor_meta is not null")
hits=[]; n=0
random.seed(1)
for i,k,dm in cur.fetchall():
    ke=parse(k or '')
    if ke is None: continue
    n+=1
    for idx,x in enumerate(dm or []):
        de=parse(str(x.get('value_latex') or x.get('value') or ''))
        if de is None: continue
        syms=sorted((ke.free_symbols|de.free_symbols),key=lambda s:s.name)
        if not syms: continue
        ok=0;bad=False
        for _ in range(6):
            vals=[random.uniform(0.3,2.4) for _ in syms]
            a=num(ke,syms,vals); b=num(de,syms,vals)
            if a is None or b is None: continue
            ok+=1
            if abs(a-b)>1e-7*max(1,abs(a)): bad=True;break
        if ok>=3 and not bad: hits.append((i,idx,k,x.get('value_latex') or x.get('value')))
print('parsed keys',n,'hits',len(hits))
json.dump(hits,open('expr_hits.json','w'),ensure_ascii=False)
for h in hits[:80]: print(h)
