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
    for g,L in [('\\alpha','A'),('\\beta','B'),('\\gamma','G'),('\\theta','T'),('\\varphi','F'),('\\phi','F'),('\\varepsilon','E'),('\\delta','D')]: s=s.replace(g,L)
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
    s=re.sub(r'(sin|cos|tan|cot|log10|log)\s*\^\{?(\d+)\}?\s*([A-Za-z0-9(]+)',lambda m:f'({m.group(1)}({m.group(3)}))**{m.group(2)}',s)
    s=re.sub(r'(sin|cos|tan|cot|log10|log)\s+([A-Za-z0-9]+)',r'\1(\2)',s)
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

cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex ~* '(Упростите|Преобразуйте|Вычислите|Найдите значение|Сократите)'")
random.seed(3); n=0; bad=[]
for i,q,k in cur.fetchall():
    ms=re.findall(r'\$([^$]+)\$',q or '')
    if len(ms)!=1: continue
    if not re.search(r'\\(sin|cos|tg|ctg|alpha|beta)',ms[0]) : continue
    qe=parse(ms[0]); ke=parse(k or '')
    if qe is None or ke is None: continue
    syms=sorted((qe.free_symbols|ke.free_symbols),key=lambda s:s.name)
    ok=0;mis=False
    for _ in range(8):
        vals=[random.uniform(0.3,1.2) for _ in syms]
        a=num(qe,syms,vals); b=num(ke,syms,vals)
        if a is None or b is None: continue
        ok+=1
        if abs(a-b)>1e-6*max(1,abs(a)): mis=True;break
    if ok>=3:
        n+=1
        if mis: bad.append((i,ms[0][:70],k[:60]))
print('checked',n,'mismatch',len(bad))
for b in bad: print(b)
